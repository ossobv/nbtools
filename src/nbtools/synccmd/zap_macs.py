from ..command import SyncCommand
from ..exceptions import UnrecognisedItem
from ..netbox import get_mac_addresses
from ..types import MacAddr
from ..util import quoted_name
from ..work import DeleteMacAddress, named_id


class ZapMacAddressCommand(SyncCommand):
    name = 'zap-macaddress'
    help = (
        'Delete MAC address records, named on the command line. Pairs '
        'with "nblint --porcelain duplicate-macs", which prints the MACs '
        'that exist more than once and so stop set-interface-ip-by-mac '
        'from picking an interface.')

    @classmethod
    def add_arguments(cls, parser):
        # Required: it is the only mode there is, and a delete should
        # have to say what it means.
        parser.add_argument(
            '--unassigned', action='store_true', required=True, help=(
                'Delete the copies that are not assigned to anything. '
                'Currently the only mode.'))
        parser.add_argument('mac', type=MacAddr, nargs='+', help=(
            'MAC addresses to clean up (e.g. 11:22:33:44:55:66)'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_mac_addresses(args.mac)
        return cmd

    def set_mac_addresses(self, macs):
        self._macs = macs

    @staticmethod
    def _describe_kept(records):
        "Name the assigned copies that this delete leaves behind"
        if not records:
            return None

        return ', '.join(
            f'#{rec.id} {quoted_name(rec.assigned_object.device.name)}'
            f':{rec.assigned_object.name}'
            for rec in sorted(records, key=(lambda rec: rec.id)))

    def plan(self):
        work_to_do = []

        for mac in self._macs:
            records = get_mac_addresses(self.nbapi, mac)
            if not records:
                raise UnrecognisedItem(mac)

            # NOTE: nothing here refuses to remove the last copy. The
            # MACs are named on the command line, which is the operator
            # saying which ones to act on; nblint decides what to
            # suggest.
            kept_on = self._describe_kept(
                [rec for rec in records if rec.assigned_object])

            for rec in records:
                if rec.assigned_object:
                    continue

                work_to_do.append(DeleteMacAddress(
                    named_id(str(mac), rec.id, parent=None),
                    kept_on=kept_on))

        return work_to_do
