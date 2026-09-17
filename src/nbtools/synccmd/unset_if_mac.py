from collections import namedtuple

from ..command import STDIN_ARG, SyncCommand, stdin_or
from ..exceptions import (
    InvalidInput, UnrecognisedItem, UnrecognisedItemOnTarget)
from ..netbox import get_interface_tree, get_mac_addresses
from ..types import DevIface, MacAddr
from ..work import DeleteMacAddress, named_id


# One item of work when the target comes off stdin too: a
# "TARGET MAC" line apiece.
TargetMac = namedtuple('TargetMac', 'target mac')


class UnsetInterfaceMacCommand(SyncCommand):
    """
    Take MAC addresses off an interface.

    Under the hood, this simply deletes the MAC address record in NetBox.
    MACs attached to nothing are not worth keeping.

    The MACs can arrive on stdin, one per line, for the one target:

        # The ':' means the-unassigned-interface.
        nblint --porcelain duplicate-macs |
            nbsync --batch unset-interface-mac : -

    Or one can supply TARGET and MAC:

        echo 'dev:iface 11:22:33:44:55:66' |
            nbsync --batch unset-interface-mac - -
    """
    name = 'unset-interface-mac'
    help = (
        'Remove MAC addresses from an interface.\n'
        '\n'
        'Give ":" as the target to work on the records that are on no '
        'interface at all. That is how the loose copies nblint '
        'duplicate-macs finds are dropped:\n'
        '\n'
        '  nblint --porcelain duplicate-macs --limit=unassigned |\n'
        '    nbsync --batch unset-interface-mac : -\n'
        '\n'
        'With "-" for the target as well, each line names both:\n'
        '\n'
        "  echo 'mynode.example:BMC 11:22:33:44:55:66' |\n"
        '    nbsync --batch unset-interface-mac - -')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('target', type=stdin_or(DevIface), help=(
            'Target device and interface (e.g. mynode.example:BMC), or '
            '":" for the records that are not assigned to any interface. '
            f'Give "{STDIN_ARG}" for this and the MAC both to read '
            '"TARGET MAC" lines from stdin'))
        parser.add_argument(
            'mac', type=stdin_or(MacAddr), nargs='+', help=(
                'MAC addresses to remove (e.g. 11:22:33:44:55:66). Give '
                f'"{STDIN_ARG}" to read them from stdin instead, one per '
                'line. That mode requires --batch'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        if args.target == STDIN_ARG:
            cmd.set_target_rows(args.mac)
        else:
            cmd.set_target_interface(args.target)
            cmd.set_mac_addresses(args.mac)
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        # The one target for every MAC, or None when each line names
        # its own; see set_target_rows().
        self._target = None
        self._iface = None

    def set_target_interface(self, target: DevIface):
        self._target = target

    def set_mac_addresses(self, macs):
        "The MACs to take off the one target, a '-' among them off stdin"
        self.set_input_values(macs, MacAddr)

    def set_target_rows(self, macs):
        """
        Take the target off stdin, a line apiece, with the MAC or not

        '- -' reads "TARGET MAC" lines; '- MAC' reads targets and takes
        that MAC off each. More than one MAC has no row to go in.
        """
        if len(macs) != 1:
            raise InvalidInput(
                f'with the target on stdin, give one MAC or '
                f'"{STDIN_ARG}", not {len(macs)}')

        self._target = None
        self.set_input_rows(TargetMac, [
            (STDIN_ARG, DevIface), (macs[0], MacAddr)])

    def _get_target_interface(self, target):
        "The interface to clear, or None for the unassigned records"
        if target == DevIface.NONE:
            return None

        return get_interface_tree(
            self.nbapi, target, with_subinterfaces=False,
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

    @staticmethod
    def _sits_on(record, iface):
        """
        Is this MAC record on that interface, or on none at all?

        Compare the type as well as the id. A MAC search returns
        virtualization.vminterface records beside dcim.interface ones,
        and their ids come from different tables, so vminterface #5319
        is not dcim interface #5319. Getting that wrong here deletes
        the wrong record.
        """
        assigned = record.assigned_object
        if iface is None:
            return assigned is None

        return (
            assigned is not None
            and assigned.id == iface.id
            and record.assigned_object_type == 'dcim.interface')

    def prepare(self):
        "Look the one target up once, when there is one"
        if self._target is not None:
            self._iface = self._get_target_interface(self._target)

    def plan_one(self, value):
        if isinstance(value, TargetMac):
            iface = self._get_target_interface(value.target)
            mac = value.mac
        else:
            iface = self._iface
            mac = value

        nd_iface = self._named_interface(iface)

        records = get_mac_addresses(self.nbapi, mac)
        if not records:
            raise UnrecognisedItem(mac)

        return [
            DeleteMacAddress(named_id(str(mac), record.id, parent=nd_iface))
            for record in records if self._sits_on(record, iface)]
