from ..command import STDIN_ARG, SyncCommand, stdin_or
from ..exceptions import UnrecognisedItemOnTarget
from ..netbox import get_interface_tree, get_ip_addresses
from ..types import DevIface
from ..work import (
    DeleteInterface, DeleteIPAddress, ModifyInterface, named_id)


# What a zapped interface is left with, per field. The name, type,
# enabled state, cable and MAC addresses belong to the port itself
# rather than to what is configured on it, so those stay.
ZAPPED_VALUES = {
    'description': '',
    'label': '',
    'mode': None,
    'tagged_vlans': [],
    'untagged_vlan': None,
    'tags': [],
    'vrf': None,
}


def current_value(iface, key):
    """
    The field as the PATCH body would spell it, to compare against

    A choice field is its value, a nested record its id, and a list of
    nested records their ids.
    """
    value = getattr(iface, key, None)
    if isinstance(value, (list, tuple)):
        return [getattr(item, 'id', item) for item in value]
    if hasattr(value, 'value'):
        return value.value
    if hasattr(value, 'id'):
        return value.id

    return value


class ZapInterfaceCommand(SyncCommand):
    """
    Wipe what is configured on an interface, keeping the interface.

    Every subinterface is deleted, and so is every IP address on it and
    on the interface itself: deleting a subinterface in NetBox would
    only unassign its addresses, leaving them behind. The interface
    then has its description, label, 802.1Q mode, VLANs, tags and VRF
    cleared -- the fields migrate-interface copies onto a target.
    """
    name = 'zap-interface'
    help = (
        'Zap (clean/wipe) properties from an interface. '
        'Keeps the interface, its type, cable and MACs, but deletes its '
        'subinterfaces and the IPs on them and on it, and clears its '
        'description, label, mode, VLANs, tags and VRF. '
        'Useful to wipe target before calling migrate-interface.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument(
            'target', type=stdin_or(DevIface), nargs='+', help=(
                'Target device and interface (e.g. leaf2:swp8). Give '
                f'"{STDIN_ARG}" to read them from stdin instead, one '
                'per line, each zapped as it arrives -- which needs '
                '--batch, stdin being taken'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_input_values(args.target, DevIface)
        return cmd

    def plan_one(self, target: DevIface):
        tgt = get_interface_tree(
            self.nbapi, target, raise_as=UnrecognisedItemOnTarget)

        nd_dev = named_id(tgt.dev.name, tgt.dev.id, parent=None)
        work_to_do = []

        # The subinterfaces go first, their addresses before them.
        for child in tgt.if_children:
            nd_child = named_id(child.name, child.id, parent=nd_dev)
            self._delete_ips(work_to_do, child, nd_child)
            work_to_do.append(DeleteInterface(nd_child))

        parent = tgt.if_parent
        nd_parent = named_id(parent.name, parent.id, parent=nd_dev)
        self._delete_ips(work_to_do, parent, nd_parent)

        update_values = {
            key: value for key, value in ZAPPED_VALUES.items()
            if current_value(parent, key) != value}
        if update_values:
            work_to_do.append(ModifyInterface(nd_parent, update_values))

        return work_to_do

    def _delete_ips(self, work_to_do, iface, nd_iface):
        for ipaddr in get_ip_addresses(self.nbapi, iface):
            work_to_do.append(DeleteIPAddress(
                named_id(ipaddr.address, ipaddr.id, parent=nd_iface)))
