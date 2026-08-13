from ..command import Command
from ..exceptions import (
    UnrecognisedItemOnSource, UnrecognisedItemOnTarget)
from ..netbox import get_interface_tree, get_ip_addresses
from ..types import DevIface
from ..work import (
    CreateInterface, DeleteInterface, ModifyInterface,
    ModifyCable,
    ModifyIPAddress,
    find_elem, named_anon, named_id, named_lambda)


class MigrateInterfaceCommand(Command):
    name = 'migrate-interface'
    help = (
        'Migrate properties of an interface -- subinterfaces, IPs and cables '
        '-- from source to target. '
        'Target should start out empty. Source will be zapped. '
        'Useful when moving a cable from one switch to another.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('source', type=DevIface, help=(
            'Source device and interface (e.g. leaf1:swp19)'))
        parser.add_argument('target', type=DevIface, help=(
            'Target device and interface (e.g. leaf2:swp8)'))

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

    def plan(self):
        # Get source.
        src = get_interface_tree(
            self.nbapi, self._source, raise_as=UnrecognisedItemOnSource)

        # Get target.
        tgt = get_interface_tree(
            self.nbapi, self._target, raise_as=UnrecognisedItemOnTarget)

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

        nd_srcdev = named_id(
            src.dev.name, src.dev.id, parent=None)

        # Check cable and reassign.
        if src.if_parent.cable:
            # We need to adjust one end of the cable. Check which one.
            assert len(src.if_parent.cable.a_terminations) < 2
            assert len(src.if_parent.cable.b_terminations) < 2
            adjust_cable = {}
            if (src.if_parent.cable.a_terminations
                    and (src.if_parent.cable.a_terminations[0].id
                         == src.if_parent.id)):
                adjust_cable = {'a_terminations': [
                    {
                        'object_type': 'dcim.interface',
                        'object_id': tgt.if_parent.id,
                    }
                ]}
            elif (src.if_parent.cable.b_terminations
                    and (src.if_parent.cable.b_terminations[0].id
                         == src.if_parent.id)):
                adjust_cable = {'b_terminations': [
                    {
                        'object_type': 'dcim.interface',
                        'object_id': tgt.if_parent.id,
                    }
                ]}
            nd_srciface = named_id(
                src.if_parent.name, src.if_parent.id, parent=nd_srcdev)
            work_to_do.append(
                ModifyCable(
                    named_id(
                        f'{src.if_parent.cable}',
                        src.if_parent.cable.id, parent=nd_srciface),
                    adjust_cable))

        # Add work for the parent interface.
        self._add_work(
            work_to_do, src, tgt, src.if_parent, tgt.if_parent, tgt.if_name)

        # For child interface do the same.
        for srciface in src.if_children:
            # From "ensrc1.1234" make "entgt2.1234".
            srcifacesuffix = srciface.name[len(src.if_name):]
            assert srcifacesuffix.startswith('.'), srcifacesuffix
            tgtifacename = f'{tgt.if_name}{srcifacesuffix}'
            tgtiface = find_elem(
                tgt.if_children, (lambda x: x.name == tgtifacename))

            self._add_work(
                work_to_do, src, tgt, srciface, tgtiface, tgtifacename)

            work_to_do.append(
                DeleteInterface(
                    named_id(srciface.name, srciface.id, parent=nd_srcdev)))

        return work_to_do

    def _add_work(
            self, work_to_do, src, tgt, srciface, tgtiface, tgtifacename):
        # Get source IPs.
        srcipaddrs = get_ip_addresses(self.nbapi, srciface)

        nd_srcdev = named_id(
            src.dev.name, src.dev.id, parent=None)
        nd_srciface = named_id(
            srciface.name, srciface.id, parent=nd_srcdev)
        nd_tgtdev = named_id(
            tgt.dev.name, tgt.dev.id, parent=None)

        if tgtiface:
            # Assume we're dealing with the parent interface here.
            assert tgtiface == tgt.if_parent, (tgt.if_parent, tgtiface)

            nd_tgtiface = named_id(
                tgtiface.name, tgtiface.id, parent=nd_tgtdev)
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
        else:
            nd_tgtiface = named_anon(tgtifacename, parent=nd_tgtdev)
            nd_vrf = (
                named_id(srciface.vrf.name, srciface.vrf.id, parent=None)
                if srciface.vrf else named_id('-', None, parent=None))

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

        for srcipaddr in srcipaddrs:
            # Do we assert that both source and dest are dcim.interface?
            work_to_do.append(
                ModifyIPAddress(
                    named_id(srcipaddr.address, srcipaddr.id, parent=(
                        nd_srciface)),
                    {
                        'assigned_object_type': 'dcim.interface',
                        'assigned_object_id': (
                            named_lambda(f'&({tgtifacename})', (
                                lambda nbapi: (
                                    nbapi.dcim.interfaces.get(
                                        device_id=tgt.dev.id,
                                        name=tgtifacename).id)),
                                parent=None)),
                    }
                )
            )
