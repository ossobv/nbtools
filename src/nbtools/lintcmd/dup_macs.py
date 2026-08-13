from collections import namedtuple

from ..command import LintCommand
from ..util import quoted_name


# Values that are placeholders rather than identities. NetBox fills
# these in when something is unknown, so holding one twice says
# nothing about anything.
NOT_REAL_MACS = frozenset((
    '00:00:00:00:00:00',
    'ff:ff:ff:ff:ff:ff',
))

# What --limit takes. Only the one so far, but it reads as a choice
# rather than as a flag, and the other kinds this reports -- the same
# MAC on two machines -- will want naming here in time.
LIMIT_UNASSIGNED = 'unassigned'
LIMITS = (LIMIT_UNASSIGNED,)


def holder(iface):
    """
    The device or virtual machine an interface belongs to, and which

    A dcim.interface has .device. A virtualization.vminterface has
    .virtual_machine instead, and one MAC address search hands back
    both kinds. Which one it is belongs to the identity: the two come
    from different tables, so device #5 and virtual machine #5 are not
    the same machine.

    Returns (None, None) for an interface shaped like neither.
    """
    device = getattr(iface, 'device', None)
    if device is not None:
        return ('device', device)

    virtual_machine = getattr(iface, 'virtual_machine', None)
    if virtual_machine is not None:
        return ('virtual_machine', virtual_machine)

    return (None, None)


class DuplicateMacs(
        namedtuple('DuplicateMacs', 'mac assigned unassigned')):
    "One MAC value NetBox holds more than once, split by attachment"

    @property
    def is_explained(self):
        """
        True when sharing this MAC is the normal state of affairs.

        A bridge and its members, a parent and its subinterfaces, and
        the members of a LAG all carry one MAC on purpose, and they
        look alike: every copy is assigned, they sit on one device, and
        each is on an interface of its own.

        The double-creation mistake never looks like that. Its spare
        copy is assigned to nothing, so it has no device at all.

        This goes by the device rather than by the parent/bridge
        relationship, which would say it exactly. The interface nested
        in a MAC record is a brief one -- id, name, device -- so asking
        which interface a copy hangs off would cost a GET apiece across
        the whole MAC table. Hence --all, for when this guesses wrong.
        """
        if self.unassigned:
            return False

        ifaces = [rec.assigned_object for rec in self.assigned]

        holders = set()
        for iface in ifaces:
            kind, machine = holder(iface)
            if machine is None:
                # Shaped like neither a device nor a VM interface. We
                # cannot say it is fine, so we do not.
                return False

            holders.add((kind, machine.id))

        # The same MAC on two machines is a real mistake, e.g. a NIC
        # moved without anyone cleaning up behind it.
        if len(holders) > 1:
            return False

        # Two records on one interface is never a bridge.
        return len({iface.id for iface in ifaces}) == len(ifaces)


def get_duplicate_macs(nbapi):
    """
    Find MAC addresses that NetBox holds more than once

    Returns a list of DuplicateMacs ordered by MAC address, each
    holding the records that have an assigned_object and those that do
    not. A MAC recorded only once is not returned at all.

    The usual cause is someone creating the MAC twice and assigning
    only the second one. Duplicates are a problem in their own right:
    set-interface-ip-by-mac refuses to guess between them.
    """
    by_mac = {}
    for mac in nbapi.dcim.mac_addresses.all():
        value = str(mac.mac_address).lower()
        if value in NOT_REAL_MACS:
            continue

        by_mac.setdefault(value, []).append(mac)

    duplicates = []
    for value, records in sorted(by_mac.items()):
        if len(records) < 2:
            continue

        duplicates.append(DuplicateMacs(
            mac=value,
            assigned=[rec for rec in records if rec.assigned_object],
            unassigned=[rec for rec in records if not rec.assigned_object],
        ))

    return duplicates


def where(record):
    "Render where a MAC record is attached, or 'unassigned'"
    iface = record.assigned_object
    if not iface:
        return 'unassigned'

    _kind, machine = holder(iface)
    name = (machine.name if machine is not None else '?')

    return f'{quoted_name(name)}:{iface.name}'


class DuplicateMacFinding:
    "One MAC address that NetBox holds more than once"

    def __init__(self, duplicate):
        self.duplicate = duplicate

    def porcelain(self):
        "The MAC, ready to hand to nbsync unset-interface-mac"
        return self.duplicate.mac

    def _note(self):
        if self.duplicate.is_explained:
            # Only reachable under --all.
            return ' (shared within one device)'

        # Worth calling out: there is no copy here to keep, so cleaning
        # this one up drops the MAC from NetBox altogether.
        if not self.duplicate.assigned:
            return ' (none assigned)'

        return ''

    def __str__(self):
        dup = self.duplicate
        records = dup.assigned + dup.unassigned
        detail = ', '.join(
            f'#{rec.id} {where(rec)}'
            for rec in sorted(records, key=(lambda rec: rec.id)))

        return f'{dup.mac} x{len(records)}: {detail}{self._note()}'


class DuplicateMacsCommand(LintCommand):
    name = 'duplicate-macs'
    help = (
        'Find MAC addresses that exist more than once. Usually someone '
        'created the MAC twice and assigned only the second one, which '
        'leaves set-interface-ip-by-mac unable to pick between them.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--all', action='store_true', help=(
            'Report the duplicates that are explained too: bridges, '
            'subinterfaces and LAG members share a MAC on purpose.'))
        parser.add_argument('--limit', choices=LIMITS, help=(
            'Report only one kind of duplicate. "unassigned" is the ones '
            'holding a copy that is on no interface, which is what '
            'unset-interface-mac can clear out.'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_report_all(args.all)
        cmd.set_limit(args.limit)
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._report_all = False
        self._limit = None

    def set_report_all(self, report_all=True):
        self._report_all = report_all

    def set_limit(self, limit):
        assert limit in LIMITS or limit is None, limit
        self._limit = limit

    def _wanted(self, duplicate):
        if self._limit == LIMIT_UNASSIGNED:
            # No need to consult is_explained or --all here: a group
            # holding an unassigned copy is never explained.
            return bool(duplicate.unassigned)

        return self._report_all or not duplicate.is_explained

    def find(self):
        return [
            DuplicateMacFinding(duplicate)
            for duplicate in get_duplicate_macs(self.nbapi)
            if self._wanted(duplicate)]
