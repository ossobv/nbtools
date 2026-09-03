from collections import namedtuple

from ..command import LintCommand
from ..util import (
    mac_from_interface_name, quoted_name, split_subinterface)


# Values that are placeholders rather than identities. Some sources
# show one of these (especially the NUL one), so it's not uncommon
# to see duplicates of those.
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


def family_of(iface):
    """
    The key of the group of interfaces this one shares a MAC with

    swp1 and swp1.2107 on one device are one family: a subinterface
    carries its parent's MAC, and is supposed to. So both map to
    ('device', 400, 'swp1') and a listing can show the parent once
    instead of the port and each of its VLANs.

    An interface that is shaped like neither a device nor a VM one
    gets a family of its own, keyed by id: we cannot place it, so we
    do not fold anything into it.
    """
    kind, machine = holder(iface)
    if machine is None:
        return (None, None, iface.id)

    split = split_subinterface(iface.name)
    base = (split[0] if split else str(iface.name))

    return (kind, machine.id, base)


def collapse_subinterfaces(records):
    """
    Fold each family's subinterface records into the parent's entry

    Returns [(record, folded)] where record is the one to show and
    folded is how many subinterface records it stands for. Ordered by
    record id.

    Within a family the entry shown is the record on the interface
    named like the family -- the parent -- and the rest are counted.
    With no such record, the interface with the lowest id stands in;
    its name still says which port the family is on.

    Records that sit on the *same* interface are all kept. Two MAC
    records on one interface is a finding in its own right, and
    counting one of them as a subinterface would hide it.
    """
    families = {}
    for record in records:
        families.setdefault(
            family_of(record.assigned_object), []).append(record)

    entries = []
    for family, found in families.items():
        _kind, _machine_id, base = family
        by_iface = {}
        for record in found:
            by_iface.setdefault(record.assigned_object.id, []).append(record)

        shown_id = None
        for iface_id, on_it in by_iface.items():
            if str(on_it[0].assigned_object.name) == base:
                shown_id = iface_id
                break
        else:
            shown_id = min(by_iface)

        folded = sum(
            len(on_it) for iface_id, on_it in by_iface.items()
            if iface_id != shown_id)

        for record in by_iface[shown_id]:
            entries.append((record, folded))
            folded = 0  # only the first entry carries the count

    return sorted(entries, key=(lambda entry: entry[0].id))


class DuplicateMacs(
        namedtuple('DuplicateMacs', 'mac assigned unassigned')):
    "One MAC value NetBox holds more than once, split by attachment"

    @property
    def is_self_named(self):
        """
        True when every copy sits on an interface named after this MAC.

        systemd names a NIC with no stable bus path after its own
        address -- enxbe3af2b6059f is be:3a:f2:b6:05:9f -- so a record
        on such an interface cannot be a mistaken copy of something
        else: the name only exists because the address does.

        Certain machines have a builtin NIC with a non-unique MAC.
        Ignore those.
        """
        if not self.assigned:
            return False

        return all(
            mac_from_interface_name(rec.assigned_object.name) == self.mac
            for rec in self.assigned)

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

        is_self_named above is the one case where the brief record
        does say it exactly, because there the answer is in the name.
        """
        if self.unassigned:
            return False

        # A copy on no interface is garbage whatever the others look
        # like, which is why this comes after the check above.
        if self.is_self_named:
            return True

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


def folded_as(folded):
    "Account for the subinterface records that are not listed"
    if not folded:
        return ''

    return f' +{folded} sub'


class DuplicateMacFinding:
    "One MAC address that NetBox holds more than once"

    def __init__(self, duplicate):
        self.duplicate = duplicate

    def porcelain(self):
        "The MAC, ready to hand to nbsync unset-interface-mac"
        return self.duplicate.mac

    def _note(self):
        # Reachable under --all, and also without it when an
        # unassigned copy drags the group into the report anyway --
        # where it is the useful half of the line, since it says the
        # assigned copies are fine and the loose one is the finding.
        if self.duplicate.is_self_named:
            return ' (interfaces named after this mac)'

        # This one is only reachable under --all.
        if self.duplicate.is_explained:
            return ' (shared within one device)'

        # Worth calling out: there is no copy here to keep, so cleaning
        # this one up drops the MAC from NetBox altogether.
        if not self.duplicate.assigned:
            return ' (none assigned)'

        return ''

    def __str__(self):
        """
        The MAC, how many records hold it, and where each one sits.

        Subinterfaces are folded into their parent: they are supposed
        to carry the parent's MAC, so listing swp1 and each of its
        VLANs separately buries whatever the real conflict is. The
        count at the front is still every record, and the '+N sub'
        markers account for the ones not listed.
        """
        dup = self.duplicate
        parts = [
            f'#{rec.id} {where(rec)}{folded_as(folded)}'
            for rec, folded in collapse_subinterfaces(dup.assigned)]
        parts.extend(
            f'#{rec.id} {where(rec)}'
            for rec in sorted(dup.unassigned, key=(lambda rec: rec.id)))

        total = len(dup.assigned) + len(dup.unassigned)

        return f'{dup.mac} x{total}: {", ".join(parts)}{self._note()}'


class DuplicateMacsCommand(LintCommand):
    name = 'duplicate-macs'
    help = (
        'Find MAC addresses that exist more than once. Could be someone '
        'who created the MAC twice and assigned only the second one. Or '
        'the device was renamed and then rediscovered. Generally you '
        'expect only unique MAC addresses in your entire NetBox. '
        'NOTE: Some devices have a enxbe3af2b6059f device which is '
        'non-unique. We ignore the enx<MAC> devices, unless --all '
        'is specified.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--all', action='store_true', help=(
            'Report the duplicates that are explained too: bridges, '
            'subinterfaces and LAG members share a MAC on purpose.'))
        parser.add_argument('--limit', choices=LIMITS, help=(
            'Report only one kind of duplicate. "unassigned" reports the '
            'ones holding a copy that is on no interface.'))

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
