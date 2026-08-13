from collections import namedtuple
from ipaddress import IPv4Interface
from warnings import warn

from ..command import Command
from ..device import NetboxDevice
from ..exceptions import (
    NotFound, UnrecognisedItemOnSource, UnrecognisedItemOnTarget)
from ..types import DevIface
from ..work import (
    CreateInterface, ModifyInterface,
    AssignIPAddress, ModifyIPAddress,
    find_elem, named_anon, named_id, named_lambda)


# If any of the interface tags is one of these, we skip the cloning.
NO_CLONE_TAGS = frozenset({'CLOSSO_ROTH'})

CloneInterfaceInfo = namedtuple(
    'CloneInterfaceInfo', 'dev if_name if_parent if_children')


class CloneInterfaceCommand(Command):
    name = 'clone-interface'
    help = (
        'Clone interface with subinterfaces from source to target. '
        'Useful when having a machine connected to multiple interfaces. '
        'It will duplicate the virtual child interfaces. '
        'It will copy the IPv4 addresses to the appropriate child (vlan) '
        'interfaces. '
        'It sets role=anycast on the IPs so they can be assigned to multiple '
        'interfaces.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('source', type=DevIface, help=(
            'Source device and interface (e.g. leaf1:swp19)'))
        parser.add_argument('target', type=DevIface, help=(
            'Target device and interface (e.g. leaf2:swp19)'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_source_interface(args.source)
        cmd.set_target_interface(args.target)
        return cmd

    def set_source_interface(self, source: DevIface):
        self._source = source

    def set_target_interface(self, target: DevIface):
        self._target = target

    @staticmethod
    def _check_that_child_interface_names_start_with_interface(
            ifaces, ifacename) -> None:
        startswith = f'{ifacename}.'
        for iface in ifaces:
            if not iface.name.startswith(startswith):
                raise NotImplementedError(
                    f'expected "{iface}" to start with "{startswith}"')

    def _make_cloneinterfaceinfo(self, devif: DevIface) -> CloneInterfaceInfo:
        dev = NetboxDevice.get_by_name(self.nbapi, devif.device)
        ifaces = dev.get_interfaces_by_name(devif.interface)
        parentiface = ifaces.pop(0)
        self._check_that_child_interface_names_start_with_interface(
            ifaces, devif.interface)

        return CloneInterfaceInfo(
            dev=dev,
            if_name=devif.interface,
            if_parent=parentiface,
            if_children=ifaces,
        )

    def plan(self):
        # Get source.
        try:
            src = self._make_cloneinterfaceinfo(self._source)
        except NotFound as e:
            raise UnrecognisedItemOnSource(self._source) from e

        # Get target.
        try:
            tgt = self._make_cloneinterfaceinfo(self._target)
        except NotFound as e:
            raise UnrecognisedItemOnTarget(self._target) from e

        # For each interface, check ip addresses.
        # Step one: check for excess target interfaces.
        srcifaces_tst = {
            iface.name[len(src.if_name):] for iface in src.if_children}
        tgtifaces_tst = {
            iface.name[len(tgt.if_name):] for iface in tgt.if_children}
        if excess_ifaces := (tgtifaces_tst - srcifaces_tst):
            excess_ifaces = [f'{tgt.if_name}{i}' for i in excess_ifaces]
            raise UnrecognisedItemOnTarget(
                f'excess interfaces on target: {excess_ifaces}')

        # Build a list of future work.
        work_to_do = []

        # Properties of the parent interface.
        self._add_work(
            work_to_do, src, tgt, src.if_parent, tgt.if_parent, tgt.if_name)

        # For each source, check target.
        for srciface in src.if_children:
            if srciface.tags and any(
                    tag.name in NO_CLONE_TAGS for tag in srciface.tags):
                warn(
                    f'Skipping {srciface} because {srciface.tags} '
                    f'in NO_CLONE_TAGS')
                continue

            # From "ensrc1.1234" make "entgt2.1234".
            srcifacesuffix = srciface.name[len(src.if_name):]
            assert srcifacesuffix.startswith('.'), srcifacesuffix
            tgtifacename = f'{tgt.if_name}{srcifacesuffix}'
            tgtiface = find_elem(
                tgt.if_children, (lambda x: x.name == tgtifacename))

            self._add_work(
                work_to_do, src, tgt, srciface, tgtiface, tgtifacename)

        return work_to_do

    def _add_work(
            self, work_to_do, src, tgt, srciface, tgtiface, tgtifacename):
        # Get source IPs.
        srcipaddrs = src.dev.get_ip_addresses_by_interface(srciface)

        # Check source. We expect a VRF on it.
        if srcipaddrs and not srciface.vrf:
            raise UnrecognisedItemOnSource(
                f'missing VRF on {src.dev.device.name}:{srciface}')

        nd_srcdev = named_id(
            src.dev.device.name, src.dev.device.id, parent=None)
        nd_srciface = named_id(
            srciface.name, srciface.id, parent=nd_srcdev)
        nd_tgtdev = named_id(
            tgt.dev.device.name, tgt.dev.device.id, parent=None)

        # Target interface does not exist yet?
        if not tgtiface:
            nd_tgtiface = named_anon(tgtifacename, parent=nd_tgtdev)

            work_to_do.append(
                CreateInterface(
                    nd_tgtiface,
                    {
                        # New data.
                        'name': tgtifacename,
                        'device': tgt.dev.device.id,
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
                        'vrf': named_id(
                            srciface.vrf.name, srciface.vrf.id, parent=None),
                    }
                )
            )
            for srcipaddr in srcipaddrs:
                if not srcipaddr.role or srcipaddr.role.value != 'anycast':
                    work_to_do.append(
                        ModifyIPAddress(
                            named_id(srcipaddr.address, srcipaddr.id, parent=(
                                nd_srciface)),
                            {'role': 'anycast'}
                        )
                    )

                nd_vrf = (
                    named_id(srcipaddr.vrf.name, srcipaddr.vrf.id, parent=None)
                    if srcipaddr.vrf else named_id('-', None, parent=None))

                # XXX: Not touched by tests!
                work_to_do.append(
                    AssignIPAddress(
                        named_anon(srcipaddr, parent=nd_tgtiface),
                        {
                            # New data.
                            'assigned_object_type': 'dcim.interface',
                            'assigned_object_id': (
                                named_lambda(f'&({tgtifacename})', (
                                    lambda nbapi: (
                                        nbapi.dcim.interfaces.get(
                                            device_id=tgt.dev.device.id,
                                            name=tgtifacename).id)),
                                    parent=nd_tgtiface)),
                            # Copied data.
                            'address': srcipaddr.address,
                            'description': srcipaddr.description,
                            'dns_name': srcipaddr.dns_name,
                            'role': 'anycast',
                            'status': srcipaddr.status.value,
                            'tags': [tag.id for tag in srcipaddr.tags],
                            'tenant': getattr(srcipaddr.tenant, 'id', None),
                            'vrf': nd_vrf,
                        }
                    )
                )
        else:
            nd_tgtiface = named_id(tgtifacename, tgtiface.id, parent=nd_tgtdev)

            nd_vrf = (
                named_id(srciface.vrf.name, srciface.vrf.id, parent=None)
                if srciface.vrf else named_id('-', None, parent=None))

            target_values = {
                'description': srciface.description,
                'enabled': srciface.enabled,
                'label': srciface.label,
                'mode': getattr(srciface.mode, 'value', None),
                'tags': [tag.id for tag in srciface.tags],
                'tagged_vlans': [vlan.id for vlan in srciface.tagged_vlans],
                'type': getattr(srciface.type, 'value', None),
                'untagged_vlan': getattr(srciface.untagged_vlan, 'id', None),
                'vrf': nd_vrf,
            }
            update_values = {}
            for key, value in target_values.items():
                attr = getattr(tgtiface, key)
                if hasattr(attr, 'value'):
                    same = (attr.value == value)
                elif hasattr(attr, 'id'):
                    if hasattr(value, 'id'):
                        same = (attr.id == value.id)
                    else:
                        same = (attr.id == value)  # eewww.. for untagged_vlan
                elif hasattr(value, 'id'):
                    # Quick fix for named_id VRF.
                    same = (attr == value.id)
                else:
                    same = (attr == value)
                if not same:
                    update_values[key] = value

            if update_values:
                work_to_do.append(ModifyInterface(nd_tgtiface, update_values))

            # Get target IPs.
            tgtipaddrs = tgt.dev.get_ip_addresses_by_interface(tgtiface)

            # Check target IPs for excess entries.
            srcipaddrs_tst = {
                # XXX: fixme: "family":{"value":4,"label":"IPv4"}
                IPv4Interface(ipaddr.address) for ipaddr in srcipaddrs}
            tgtipaddrs_tst = {
                IPv4Interface(ipaddr.address) for ipaddr in tgtipaddrs}
            if excess_ips := (tgtipaddrs_tst - srcipaddrs_tst):
                assert False, (
                    f'IPs in target iface not seen on src: {excess_ips}')

            # Get unset subset of IPs.
            for srcipaddr in srcipaddrs:
                tgtipaddr = find_elem(
                    tgtipaddrs, (lambda x: x.address == srcipaddr.address))

                if tgtipaddr:
                    if not (tgtipaddr.address == srcipaddr.address
                            and tgtipaddr.family == srcipaddr.family
                            and tgtipaddr.role == srcipaddr.role
                            and tgtipaddr.vrf == srcipaddr.vrf):
                        raise UnrecognisedItemOnTarget(
                            f'existing IP on target has different parameters: '
                            f'{srcipaddr.address}')
                else:
                    if not srcipaddr.role or srcipaddr.role.value != 'anycast':
                        work_to_do.append(
                            ModifyIPAddress(
                                named_id(
                                    srcipaddr.address, srcipaddr.id,
                                    parent=nd_srciface),
                                {'role': 'anycast'}
                            )
                        )

                    nd_vrf = (
                        named_id(
                            srcipaddr.vrf.name, srcipaddr.vrf.id, parent=None)
                        if srcipaddr.vrf else named_id('-', None, parent=None))

                    work_to_do.append(
                        AssignIPAddress(
                            named_anon(srcipaddr.address, parent=nd_tgtiface),
                            {
                                # New data.
                                'assigned_object_type': 'dcim.interface',
                                'assigned_object_id': tgtiface.id,
                                # Copied data.
                                'address': srcipaddr.address,
                                'description': srcipaddr.description,
                                'dns_name': srcipaddr.dns_name,
                                'role': 'anycast',
                                'status': srcipaddr.status.value,
                                'tags': [tag.id for tag in srcipaddr.tags],
                                'tenant': getattr(
                                    srcipaddr.tenant, 'id', None),
                                'vrf': nd_vrf,
                            }
                        )
                    )
