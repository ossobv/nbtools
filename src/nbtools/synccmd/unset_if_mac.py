from ..command import SyncCommand
from ..exceptions import UnrecognisedItem, UnrecognisedItemOnTarget
from ..netbox import get_interface_tree, get_mac_addresses
from ..types import DevIface, MacAddr
from ..work import DeleteMacAddress, named_id


class UnsetInterfaceMacCommand(SyncCommand):
    """
    Take MAC addresses off an interface.

    Removing the record is the whole of it, the way set-interface-ip
    deletes the IPs it finds in excess: a MAC address in NetBox exists
    to say which interface it is on, so a MAC that is on no interface
    is not worth keeping.
    """
    name = 'unset-interface-mac'
    help = (
        'Remove MAC addresses from an interface. Give ":" as the target '
        'to work on the records that are on no interface at all.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('target', type=DevIface, help=(
            'Target device and interface (e.g. mynode.example:BMC), or '
            '":" for the records that are not assigned to any interface'))
        parser.add_argument('mac', type=MacAddr, nargs='+', help=(
            'MAC addresses to remove (e.g. 11:22:33:44:55:66)'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_target_interface(args.target)
        cmd.set_mac_addresses(args.mac)
        return cmd

    def set_target_interface(self, target: DevIface):
        self._target = target

    def set_mac_addresses(self, macs):
        self._macs = macs

    def _get_target_interface(self):
        "The interface to clear, or None for the unassigned records"
        if self._target == DevIface.NONE:
            return None

        return get_interface_tree(
            self.nbapi, self._target, with_subinterfaces=False,
            raise_as=UnrecognisedItemOnTarget).if_parent

    @staticmethod
    def _named_interface(iface):
        "Name the target the way the other work lines name theirs"
        if iface is None:
            # Renders as ':', matching how it is spelled as an argument.
            nd_dev = named_id('', None, parent=None)
            return named_id('', None, parent=nd_dev)

        nd_dev = named_id(iface.device.name, iface.device.id, parent=None)
        return named_id(iface.name, iface.id, parent=nd_dev)

    def plan(self):
        iface = self._get_target_interface()
        nd_iface = self._named_interface(iface)
        wanted_id = (iface.id if iface else None)

        work_to_do = []

        for mac in self._macs:
            records = get_mac_addresses(self.nbapi, mac)
            if not records:
                raise UnrecognisedItem(mac)

            for record in records:
                assigned = record.assigned_object
                if (assigned.id if assigned else None) != wanted_id:
                    continue

                work_to_do.append(DeleteMacAddress(
                    named_id(str(mac), record.id, parent=nd_iface)))

        return work_to_do
