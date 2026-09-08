from ..command import LintCommand
from ..ipam import IpamIndex, address_of, address_sort_key
from ..netbox import get_all_ip_addresses, get_all_prefixes

from .findings import IpFinding


# The biggest network that still counts as a parent, per family, as a
# mask length.
DEFAULT_MIN_PREFIXLEN = {4: 24, 6: 48}

# The families --family takes. Spelled as the strings NetBox uses in
# the query, converted to int for the filter.
FAMILIES = ('4', '6')


def find_unparented_ips(prefixes, addresses, min_prefixlen=None):
    """
    The addresses that no prefix of the wanted size covers

    Returns [(ipaddr, wanted, covering)] where covering holds the masks
    of the prefixes that do cover the address, longest first, and is
    empty when nothing covers it at all.

    A host prefix counts: a /32 recorded as a prefix is a /24 or
    smaller, because it is smaller. It is a strange thing to have and
    empty-prefixes will have something to say about it, but it is not
    this finding.
    """
    if min_prefixlen is None:
        min_prefixlen = DEFAULT_MIN_PREFIXLEN

    index = IpamIndex(prefixes, addresses)

    found = []
    for ipaddr in addresses:
        wanted = min_prefixlen[address_of(ipaddr).version]
        if index.covering_prefixlens(ipaddr, down_to=wanted):
            continue

        # Only now is the wider walk worth its lookups: the note wants
        # to say whether there is a bigger prefix or nothing at all,
        # and that question is only asked about the ones that failed.
        found.append((ipaddr, wanted, index.covering_prefixlens(ipaddr)))

    return sorted(found, key=(lambda item: address_sort_key(item[0])))


def a_note(wanted, covering):
    "Say what was found instead of the prefix that should be there"
    if not covering:
        return f'(no parent prefix, wanted /{wanted} or smaller)'

    return f'(covered by /{covering[0]}, wanted /{wanted} or smaller)'


class UnparentedIpsCommand(LintCommand):
    name = 'unparented-ips'
    help = (
        'Find IP addresses that no prefix of a sensible size covers. Every '
        'address is supposed to sit in a prefix of /24 or smaller (/48 for '
        'IPv6).')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--family', choices=FAMILIES, help=(
            'Report only this address family. Both, by default.'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_family(args.family)
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._family = None

    def set_family(self, family):
        assert family in FAMILIES or family is None, family
        self._family = family

    def find(self):
        return [
            IpFinding(ipaddr, note=a_note(wanted, covering))
            for ipaddr, wanted, covering in find_unparented_ips(
                get_all_prefixes(self.nbapi, family=self._family),
                get_all_ip_addresses(self.nbapi, family=self._family))]
