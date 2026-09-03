from ..command import LintCommand
from ..ipam import IpamIndex, prefix_sort_key
from ..netbox import get_all_ip_addresses, get_all_prefixes

from .findings import PrefixFinding
from .statusarg import StatusArgument


# The families --family takes. Spelled as the strings NetBox uses in
# the query, converted to int for the filter.
FAMILIES = ('4', '6')

# The --status flag: which prefixes get reported.
#
# Reserved is the one left out by default. Container is deliberately
# *not*: a container is meant to hold other prefixes rather than
# addresses, but an empty container holds neither, so it is a finding
# -- name the statuses without it to drop those.
STATUS = StatusArgument(
    'prefixes', ('container', 'reserved', 'deprecated', 'active'),
    skipped_by_default=('reserved',),
    reason=(
        'a reserved prefix is a range somebody else hands the addresses '
        'out of, so empty is its normal state'))


def find_empty_prefixes(prefixes, addresses, statuses=None):
    """
    The prefixes that hold neither an address nor a smaller prefix.

    Both arguments are whole tables. Containment is worked out per
    VRF: a prefix in one VRF is not filled by an address in another,
    which is the same assumption duplicate-ips checks the other side
    of. The optional statuses is a StatusFilter; without one, every
    status counts.
    """
    index = IpamIndex(prefixes, addresses)

    return [
        prefix for prefix in prefixes
        if (statuses is None or statuses.allows(prefix))
        and index.is_empty_prefix(prefix)]


class EmptyPrefixesCommand(LintCommand):
    name = 'empty-prefixes'
    help = (
        'Find prefixes that hold nothing: no address and no smaller '
        'prefix inside them. They should probably not exist, and the '
        'listing gives the id to clean them up by. Reserved prefixes '
        'are skipped -- those are the ranges only partially under our '
        'control, where somebody else hands out the addresses, so this '
        'NetBox holds the prefix and not its contents. Pass '
        '--status=all to see them anyway.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--family', choices=FAMILIES, help=(
            'Report only this address family. Both, by default.'))
        STATUS.add_argument(parser)

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_family(args.family)
        cmd.set_statuses(STATUS.from_args(args))
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._family = None
        self._statuses = STATUS.filter_for()

    def set_family(self, family):
        assert family in FAMILIES or family is None, family
        self._family = family

    def set_statuses(self, statuses):
        """
        Report only prefixes with these statuses, 'all' for every one.

        Nothing, or an empty list, leaves the default in place: every
        status but the reserved.
        """
        self._statuses = STATUS.filter_for(statuses)

    def find(self):
        family = (int(self._family) if self._family else None)

        prefixes = get_all_prefixes(self.nbapi, family=family)
        addresses = get_all_ip_addresses(self.nbapi, family=family)

        return [
            PrefixFinding(prefix)
            for prefix in sorted(
                find_empty_prefixes(
                    prefixes, addresses, statuses=self._statuses),
                key=prefix_sort_key)]
