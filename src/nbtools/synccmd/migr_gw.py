from collections import namedtuple

from ..command import SyncCommand
from ..exceptions import (
    TargetCountMismatch,
    UnrecognisedItemOnSource, UnrecognisedItemOnTarget)
from ..netbox import (
    get_interface_by_id, get_interface_tree, get_ip_addresses,
    get_ip_addresses_by_address, get_vm, get_vm_interfaces,
    get_vm_ip_addresses)
from ..types import DevIface, Hostname
from ..util import natsort_key, peer_address
from ..work import (
    CreateInterface, DeleteInterface,
    DummyUnassignIPAddress, ReassignIPAddress,
    find_elem, named_anon, named_id, named_lambda)


# One gateway found by walking a VM outwards: the IP record on the
# switch, the subinterface it sits on, and how that subinterface is
# named. The suffix ('.1234') is the part that carries over to the
# target port, because the layout is the same on both sides.
Gateway = namedtuple('Gateway', 'ipaddr iface parent_name suffix')


class MigrateGatewayCommand(SyncCommand):
    name = 'migrate-gateway'
    help = (
        'Migrate a VM by moving the connected gateway IPs. This is a rather '
        'custom situation where: the VM move itself is not handled here, but '
        'its gateways (/31) are moved from one switch subinterface to '
        'another. Specify one or more target L3 switches using -t. '
        'Then specify one or more VMs of which the gateways should move. '
        'The sync command ensures the VRF moves along onto the new '
        'interface.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('-t', '--target', action='append', type=DevIface,
            metavar='DEV:IFACE', help=(
                'Target device and interface (e.g. leaf1:swp8). Repeat it '
                'once for every switch port the gateways sit on now: the '
                'Nth --target takes the Nth of those ports, sorted by '
                'device and interface name'))
        parser.add_argument('--delete-empty', action='store_true', help=(
            'Delete a source subinterface that this run leaves without IPs'))
        parser.add_argument('vm', type=Hostname, nargs='+', help=(
            'Host name of virtual machine'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_target_interfaces(args.target or [])
        cmd.set_vms(args.vm)
        if args.delete_empty:
            cmd.set_delete_empty()
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._targets = []
        self._vms = []
        self._delete_empty = False

    def set_target_interfaces(self, targets: list):
        self._targets = list(targets)

    def set_vms(self, vms: list):
        self._vms = list(vms)

    def set_delete_empty(self):
        "Also delete the source subinterfaces this run empties out"
        self._delete_empty = True

    def plan(self):
        # Recipe:
        # - get the target switchports parent (from CLI): leaf1:swp34
        #   leaf2:swp34
        # - get VMs (one or more from CLI)
        # - get IPs of those VMs
        # - get the connected peer IPs: the other half of each /31
        # - these peerIPs should be on a subinterface
        # - check the subinterfaces of the target switch port(s)
        # - do we need to create a subinterface (.1234 with the same VRF)?
        # - then move the IPs from the current subinterfaces to the new
        #   ones
        # (note that for each VM/IP the subinterfaces can be different,
        # but the subinterface layout is always the same: swp8.1234 vrf
        # X becomes swp9.1234 vrf X)

        if not self._targets:
            raise TargetCountMismatch('no --target given')

        # Get targets, in the order they were given: the pairing below
        # is positional.
        targets = [
            get_interface_tree(
                self.nbapi, target, raise_as=UnrecognisedItemOnTarget)
            for target in self._targets]

        gateways = []
        for vmname in self._vms:
            gateways.extend(self._find_gateways(vmname))

        # Group the gateways by the switch port they hang off. That is
        # what a --target replaces: one port's worth of subinterfaces
        # moves to one new port, whichever VMs they serve.
        by_port = {}
        for gateway in gateways:
            by_port.setdefault(
                (gateway.iface.device.name, gateway.parent_name),
                []).append(gateway)

        ports = sorted(by_port, key=(
            lambda port: (natsort_key(port[0]), natsort_key(port[1]))))
        if len(ports) != len(targets):
            found = ', '.join(f'{dev}:{iface}' for dev, iface in ports)
            raise TargetCountMismatch(
                f'the gateways sit on {len(ports)} switch port(s) '
                f'({found or "none"}), but {len(targets)} target(s) '
                f'were given')

        # Build a list of future work.
        work_to_do = []

        # What this run takes off which source subinterface, for
        # --delete-empty below. Keyed by interface id, because the same
        # subinterface can serve several of the named VMs.
        emptied = {}

        # The subinterfaces we already queued a create for, so a second
        # gateway going to the same place does not create it twice.
        created = set()

        for port, tgt in zip(ports, targets):
            for gateway in by_port[port]:
                self._add_work(work_to_do, gateway, tgt, created, emptied)

        if self._delete_empty:
            work_to_do.extend(self._delete_empty_work(emptied))

        return work_to_do

    def _find_gateways(self, vmname) -> list:
        "Every gateway that answers an IP of this VM"
        vm = get_vm(self.nbapi, vmname)

        gateways = []
        for vmiface in get_vm_interfaces(self.nbapi, vm):
            for vmip in get_vm_ip_addresses(self.nbapi, vmiface):
                where = f'{vm.name}:{vmiface.name} {vmip.address}'

                # The gateway is the other half of the /31. Asking
                # NetBox for the related addresses would do as well,
                # but on a point-to-point link there is nothing to
                # look up: it is the address next door.
                try:
                    gwaddr = peer_address(vmip.address)
                except ValueError as e:
                    raise UnrecognisedItemOnSource(f'{where}: {e}') from e

                # Scoped to the VRF the VM's own IP is in, because a
                # /31 is reused in every VRF: without that, a gateway
                # routed somewhere else entirely answers to the same
                # address.
                wanted_vrf = getattr(vmip.vrf, 'id', None)
                found = [
                    gwip for gwip in get_ip_addresses_by_address(
                        self.nbapi, gwaddr)
                    if getattr(gwip.vrf, 'id', None) == wanted_vrf]
                if not found:
                    raise UnrecognisedItemOnSource(
                        f'{where}: NetBox holds no {gwaddr} in vrf '
                        f'{vmip.vrf or "-"}')

                # More than one is the normal case for an anycast
                # gateway: clone-interface puts one on both switches of
                # a pair, and then both copies move.
                gateways.extend(
                    self._as_gateway(gwip, where) for gwip in found)

        return gateways

    def _as_gateway(self, gwip, where) -> Gateway:
        "Locate the switch subinterface a gateway IP sits on"
        if gwip.assigned_object_type != 'dcim.interface':
            raise UnrecognisedItemOnSource(
                f'{where}: gateway {gwip.address} is not on a device '
                f'interface but on {gwip.assigned_object_type}')

        # The one nested in the IP record is the brief interface, and
        # this needs its VRF and its parent.
        iface = get_interface_by_id(self.nbapi, gwip.assigned_object.id)

        if '.' not in iface.name:
            raise UnrecognisedItemOnSource(
                f'{where}: gateway {gwip.address} is on '
                f'{iface.device.name}:{iface.name}, not on a subinterface')

        parent_name = iface.name.rsplit('.', 1)[0]
        suffix = iface.name[len(parent_name):]

        # Same double-check as get_interfaces_by_name() does: the name
        # says one parent, the parent_id field says another, and only
        # the two together are worth trusting.
        if iface.parent and iface.parent.name != parent_name:
            raise UnrecognisedItemOnSource(
                f'{where}: gateway {gwip.address} is on '
                f'{iface.device.name}:{iface.name}, whose parent is '
                f'{iface.parent.name} and not {parent_name}')

        return Gateway(
            ipaddr=gwip, iface=iface, parent_name=parent_name, suffix=suffix)

    def _add_work(self, work_to_do, gateway, tgt, created, emptied):
        srciface = gateway.iface
        tgtifacename = f'{tgt.if_name}{gateway.suffix}'
        tgtiface = find_elem(
            tgt.if_children, (lambda x: x.name == tgtifacename))

        # Already where we want it. Say nothing, so a second run over
        # the same VMs reports that there is nothing to do.
        if tgtiface and tgtiface.id == srciface.id:
            return

        nd_tgtdev = named_id(tgt.dev.name, tgt.dev.id, parent=None)
        nd_vrf = (
            named_id(srciface.vrf.name, srciface.vrf.id, parent=None)
            if srciface.vrf else named_id('-', None, parent=None))

        if tgtiface:
            # Reuse it, but only when it is in the VRF the gateway is
            # routed in. A subinterface carrying the right VLAN in the
            # wrong VRF belongs to something else, and moving an IP
            # onto it would quietly reroute it.
            if getattr(tgtiface.vrf, 'id', None) != nd_vrf.id:
                raise UnrecognisedItemOnTarget(
                    f'{tgt.dev.name}:{tgtifacename} is in vrf '
                    f'{tgtiface.vrf or "-"}, expected {nd_vrf}')

            # Whatever else lives there stays where it is.
            nd_tgtiface = named_id(
                tgtifacename, tgtiface.id, parent=nd_tgtdev)
            nd_tgtifaceid = nd_tgtiface
        else:
            nd_tgtiface = named_anon(tgtifacename, parent=nd_tgtdev)

            if (tgt.dev.id, tgtifacename) not in created:
                created.add((tgt.dev.id, tgtifacename))
                work_to_do.append(
                    CreateInterface(
                        nd_tgtiface,
                        {
                            # New data.
                            'name': tgtifacename,
                            'device': tgt.dev.id,
                            'parent': tgt.if_parent.id,
                            # Copied data.
                            'description': srciface.description,
                            'enabled': srciface.enabled,
                            'label': srciface.label,
                            'mode': getattr(srciface.mode, 'value', None),
                            'tags': [tag.id for tag in srciface.tags],
                            'tagged_vlans': [
                                vlan.id for vlan in srciface.tagged_vlans],
                            'type': getattr(srciface.type, 'value', None),
                            'untagged_vlan': getattr(
                                srciface.untagged_vlan, 'id', None),
                            'vrf': nd_vrf,
                        }
                    )
                )

            # It does not exist yet, so its id does not either. Look it
            # up when the create above has run.
            nd_tgtifaceid = named_lambda(
                f'&({tgtifacename})',
                (lambda nbapi: nbapi.dcim.interfaces.get(
                    device_id=tgt.dev.id, name=tgtifacename).id),
                parent=None)

        nd_srcdev = named_id(
            srciface.device.name, srciface.device.id, parent=None)
        nd_srciface = named_id(
            srciface.name, srciface.id, parent=nd_srcdev)

        # Taking the IP off the old subinterface and putting it on the
        # new one is one write: an IP is assigned to one object at a
        # time. It reads as two though, and the switch it leaves is
        # rarely the switch it lands on, so say both halves out loud.
        work_to_do.append(
            DummyUnassignIPAddress(
                named_id(
                    gateway.ipaddr.address, gateway.ipaddr.id,
                    parent=nd_srciface)
            )
        )
        work_to_do.append(
            ReassignIPAddress(
                named_id(
                    gateway.ipaddr.address, gateway.ipaddr.id,
                    parent=nd_tgtiface),
                {
                    'assigned_object_type': 'dcim.interface',
                    'assigned_object_id': nd_tgtifaceid,
                }
            )
        )

        emptied.setdefault(srciface.id, (srciface, set()))[1].add(
            gateway.ipaddr.id)

    def _delete_empty_work(self, emptied) -> list:
        """
        Delete the source subinterfaces this run leaves without IPs

        Decided over the whole run rather than per VM: two of the named
        VMs can be served by one subinterface, and it is only empty
        once both of them have left it.
        """
        work_to_do = []

        for srciface, moved_ids in sorted(
                emptied.values(),
                key=(lambda x: (
                    natsort_key(x[0].device.name), natsort_key(x[0].name)))):
            staying = [
                ipaddr for ipaddr in get_ip_addresses(self.nbapi, srciface)
                if ipaddr.id not in moved_ids]
            if staying:
                continue

            nd_srcdev = named_id(
                srciface.device.name, srciface.device.id, parent=None)
            work_to_do.append(
                DeleteInterface(
                    named_id(srciface.name, srciface.id, parent=nd_srcdev)))

        return work_to_do
