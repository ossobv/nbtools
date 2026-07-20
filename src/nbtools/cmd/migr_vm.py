from collections import namedtuple
from ipaddress import IPv4Interface, IPv6Interface, ip_interface

from ..command import Command
from ..device import NetboxDevice
from ..vm import NetboxVm
from ..exceptions import NotFound
from ..work import (
    CreateInterface, DeleteInterface, ModifyInterface,
    ModifyCable,
    ModifyIPAddress,
    UnrecognisedItemOnSource, UnrecognisedItemOnTarget,
    find_elem, named_anon, named_id, named_lambda)


MigrateInterfaceInfo = namedtuple(
    'MigrateInterfaceInfo', 'dev if_name if_parent if_children')


class MigrateVmCommand(Command):
    # nbsync migrate-vm jumphost.dr.cat4.osso.cloud pve4.dr.osso.cloud

    def set_source_vm(self, srcvmname: str):
        def peer_interface(ip):
            a, b = ip.network[0], ip.network[1]
            other = b if ip.ip == a else a
            return ip_interface(f'{other}/{ip.network.prefixlen}')

        vm = NetboxVm.get_by_name(self.nbapi, srcvmname)
        ifaces = vm.get_interfaces()
        ips = []
        gws = []
        for iface in ifaces:
            for ipobj in vm.get_ip_addresses_by_interface(iface):
                if ipobj.family.value == 4:
                    ip = IPv4Interface(ipobj.address)
                    assert ip.network.prefixlen == 31, ip
                elif ip.family.value == 6:
                    ip = IPv6Interface(ipobj.address)
                    assert ip.network.prefixlen == 127, ip
                else:
                    raise NotImplementedError(ipobj.serialize())

                ips.append(ip)
                gws.append(peer_interface(ip))

        assert len(ips) == len(gws), (ips, gws)
        assert not (set(ips) & set(gws)), (ips, gws)

        # Now we have gateway IPs. Check that they all belong to the same
        # hardware devices.
        breakpoint()
        self._xxx = fixme

    def set_target_hypervisor(self, tgthypervisorname: str):
        self._xxx = fixme

#    @staticmethod
#    def _check_that_child_interface_names_start_with_interface(
#            ifaces, ifacename) -> None:
#        startswith = f'{ifacename}.'
#        for iface in ifaces:
#            if not iface.name.startswith(startswith):
#                raise NotImplementedError(
#                    f'expected "{iface}" to start with "{startswith}"')
#
#    def _make_migrateinterfaceinfo(
#            self, devname: str, ifacename: str) -> MigrateInterfaceInfo:
#        dev = NetboxDevice.get_by_name(self.nbapi, devname)
#        ifaces = dev.get_interfaces_by_name(ifacename)
#        parentiface = ifaces.pop(0)
#        self._check_that_child_interface_names_start_with_interface(
#            ifaces, ifacename)
#
#        return MigrateInterfaceInfo(
#            dev=dev,
#            if_name=ifacename,
#            if_parent=parentiface,
#            if_children=ifaces,
#        )
#
#    def _process(self):
#        # Get source.
#        try:
#            src = self._make_migrateinterfaceinfo(
#                self._srcdevname, self._srcifacename)
#        except NotFound as e:
#            raise UnrecognisedItemOnSource(
#                (self._srcdevname, self._srcifacename)) from e
#
#        # Get target.
#        try:
#            tgt = self._make_migrateinterfaceinfo(
#                self._tgtdevname, self._tgtifacename)
#        except NotFound as e:
#            raise UnrecognisedItemOnTarget(
#                (self._tgtdevname, self._tgtifacename)) from e
#
#        # For each interface, check ip addresses.
#        # Step one: check for excess target interfaces.
#        srcifaces_tst = {
#            iface.name[len(src.if_name):] for iface in src.if_children}
#        tgtifaces_tst = {
#            iface.name[len(tgt.if_name):] for iface in tgt.if_children}
#        if excess_ifaces := (tgtifaces_tst - srcifaces_tst):
#            excess_ifaces = [f'{tgt.if_name}{i}' for i in excess_ifaces]
#            raise UnrecognisedItemOnTarget(
#                f'excess interfaces on target: {excess_ifaces}')
#
#        # Build a list of future work.
#        work_to_do = []
#
#        nd_srcdev = named_id(
#            src.dev.device.name, src.dev.device.id, parent=None)
#
#        # Check cable and reassign.
#        if src.if_parent.cable:
#            # We need to adjust one end of the cable. Check which one.
#            assert len(src.if_parent.cable.a_terminations) < 2
#            assert len(src.if_parent.cable.b_terminations) < 2
#            adjust_cable = {}
#            if (src.if_parent.cable.a_terminations
#                    and (src.if_parent.cable.a_terminations[0].id
#                         == src.if_parent.id)):
#                adjust_cable = {'a_terminations': [
#                    {
#                        'object_type': 'dcim.interface',
#                        'object_id': tgt.if_parent.id,
#                    }
#                ]}
#            elif (src.if_parent.cable.b_terminations
#                    and (src.if_parent.cable.b_terminations[0].id
#                         == src.if_parent.id)):
#                adjust_cable = {'b_terminations': [
#                    {
#                        'object_type': 'dcim.interface',
#                        'object_id': tgt.if_parent.id,
#                    }
#                ]}
#            nd_srciface = named_id(
#                src.if_parent.name, src.if_parent.id, parent=nd_srcdev)
#            work_to_do.append(
#                ModifyCable(
#                    named_id(
#                        f'{src.if_parent.cable}',
#                        src.if_parent.cable.id, parent=nd_srciface),
#                    adjust_cable))
#
#        # Add work for the parent interface.
#        self._add_work(
#            work_to_do, src, tgt, src.if_parent, tgt.if_parent, tgt.if_name)
#
#        # For child interface do the same.
#        for srciface in src.if_children:
#            # From "ensrc1.1234" make "entgt2.1234".
#            srcifacesuffix = srciface.name[len(src.if_name):]
#            assert srcifacesuffix.startswith('.'), srcifacesuffix
#            tgtifacename = f'{tgt.if_name}{srcifacesuffix}'
#            tgtiface = find_elem(
#                tgt.if_children, (lambda x: x.name == tgtifacename))
#
#            self._add_work(
#                work_to_do, src, tgt, srciface, tgtiface, tgtifacename)
#
#            work_to_do.append(
#                DeleteInterface(
#                    named_id(srciface.name, srciface.id, parent=nd_srcdev)))
#
#        # Anything to do?
#        if not work_to_do:
#            print('Nothing to do')
#            return
#
#        # There is work.
#        print('-----------------')
#        print('migrate-interface')
#        print('-----------------')
#        for work in work_to_do:
#            print('-', work)
#
#        self.confirm_or_die()
#
#        for work in work_to_do:
#            work.do(self.nbapi)
#
#    def _add_work(
#            self, work_to_do, src, tgt, srciface, tgtiface, tgtifacename):
#        # Get source IPs.
#        srcipaddrs = src.dev.get_ip_addresses_by_interface(srciface)
#
#        nd_srcdev = named_id(
#            src.dev.device.name, src.dev.device.id, parent=None)
#        nd_srciface = named_id(
#            srciface.name, srciface.id, parent=nd_srcdev)
#        nd_tgtdev = named_id(
#            tgt.dev.device.name, tgt.dev.device.id, parent=None)
#
#        if tgtiface:
#            # Assume we're dealing with the parent interface here.
#            assert tgtiface == tgt.if_parent, (tgt.if_parent, tgtiface)
#
#            nd_tgtiface = named_id(
#                tgtiface.name, tgtiface.id, parent=nd_tgtdev)
#            nd_vrf = (
#                named_id(srciface.vrf.name, srciface.vrf.id, parent=None)
#                if srciface.vrf else named_id('-', None, parent=None))
#
#            target_values = {
#                'description': srciface.description,
#                'enabled': srciface.enabled,
#                'label': srciface.label,
#                'mode': getattr(srciface.mode, 'value', None),
#                'tags': [tag.id for tag in srciface.tags],
#                'tagged_vlans': [vlan.id for vlan in srciface.tagged_vlans],
#                'type': getattr(srciface.type, 'value', None),
#                'untagged_vlan': getattr(srciface.untagged_vlan, 'id', None),
#                'vrf': nd_vrf,
#            }
#            update_values = {}
#            for key, value in target_values.items():
#                attr = getattr(tgtiface, key)
#                if hasattr(attr, 'value'):
#                    same = (attr.value == value)
#                elif hasattr(attr, 'id'):
#                    if hasattr(value, 'id'):
#                        same = (attr.id == value.id)
#                    else:
#                        same = (attr.id == value)  # eewww.. for untagged_vlan
#                elif hasattr(value, 'id'):
#                    # Quick fix for named_id VRF.
#                    same = (attr == value.id)
#                else:
#                    same = (attr == value)
#                if not same:
#                    update_values[key] = value
#
#            if update_values:
#                work_to_do.append(ModifyInterface(nd_tgtiface, update_values))
#        else:
#            nd_tgtiface = named_anon(tgtifacename, parent=nd_tgtdev)
#            nd_vrf = (
#                named_id(srciface.vrf.name, srciface.vrf.id, parent=None)
#                if srciface.vrf else named_id('-', None, parent=None))
#
#            work_to_do.append(
#                CreateInterface(
#                    nd_tgtiface,
#                    {
#                        # New data.
#                        'name': tgtifacename,
#                        'device': tgt.dev.device.id,
#                        'parent': tgt.if_parent.id,
#                        # Copied data.
#                        'description': srciface.description,
#                        'enabled': srciface.enabled,
#                        'label': srciface.label,
#                        'mode': getattr(srciface.mode, 'value', None),
#                        'tags': [tag.id for tag in srciface.tags],
#                        'tagged_vlans': [
#                            vlan.id for vlan in srciface.tagged_vlans],
#                        'type': getattr(srciface.type, 'value', None),
#                        'untagged_vlan': getattr(
#                            srciface.untagged_vlan, 'id', None),
#                        'vrf': nd_vrf,
#                    }
#                )
#            )
#
#        for srcipaddr in srcipaddrs:
#            # Do we assert that both source and dest are dcim.interface?
#            work_to_do.append(
#                ModifyIPAddress(
#                    named_id(srcipaddr.address, srcipaddr.id, parent=(
#                        nd_srciface)),
#                    {
#                        'assigned_object_type': 'dcim.interface',
#                        'assigned_object_id': (
#                            named_lambda(f'&({tgtifacename})', (
#                                lambda nbapi: (
#                                    nbapi.dcim.interfaces.get(
#                                        device_id=tgt.dev.device.id,
#                                        name=tgtifacename).id)),
#                                parent=None)),
#                    }
#                )
#            )
