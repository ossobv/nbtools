from ..command import LintCommand
from ..netbox import get_duplicate_macs
from ..util import quoted_name


def where(record):
    "Render where a MAC record is attached, or 'unassigned'"
    iface = record.assigned_object
    if not iface:
        return 'unassigned'

    return f'{quoted_name(iface.device.name)}:{iface.name}'


class DuplicateMacFinding:
    "One MAC address that NetBox holds more than once"

    def __init__(self, duplicate):
        self.duplicate = duplicate

    def porcelain(self):
        "The MAC, ready to hand to nbsync zap-macaddress"
        return self.duplicate.mac

    def __str__(self):
        dup = self.duplicate
        records = dup.assigned + dup.unassigned
        detail = ', '.join(
            f'#{rec.id} {where(rec)}'
            for rec in sorted(records, key=(lambda rec: rec.id)))
        # Worth calling out: there is no copy here to keep, so cleaning
        # this one up drops the MAC from NetBox altogether.
        note = '' if dup.assigned else ' (none assigned)'

        return f'{dup.mac} x{len(records)}: {detail}{note}'


class DuplicateMacsCommand(LintCommand):
    name = 'duplicate-macs'
    help = (
        'Find MAC addresses that exist more than once. Usually someone '
        'created the MAC twice and assigned only the second one, which '
        'leaves set-interface-ip-by-mac unable to pick between them.')

    def find(self):
        return [
            DuplicateMacFinding(duplicate)
            for duplicate in get_duplicate_macs(self.nbapi)]
