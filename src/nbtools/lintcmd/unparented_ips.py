from ..command import LintCommand
from ..ipam import IpamIndex, address_of, address_sort_key
from ..netbox import get_all_ip_addresses, get_all_prefixes
from .findings import IpFinding


# The biggest network that still counts as a parent, per family, as a
# mask length. /24 is the rule DESIGN.md states, so a covering prefix
# has to be a /24 or smaller -- which is a mask of 24 or *more* bits,
# and the reason this is spelled in prefix lengths rather than in
# words. /64 for IPv6 is this tool's guess at the same rule a family
# over: the standard LAN size, and the one number that was not given,
# so --min-prefixlen6 exists to say otherwise.
DEFAULT_MIN_PREFIXLEN = {4: 24, 6: 64}


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
        'address is supposed to sit in a prefix of /24 or smaller (/64 for '
        'IPv6); an address with only a /16 above it, or with nothing above '
        'it at all, is an address nobody wrote the subnet of down.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument(
            '--min-prefixlen4', type=int, metavar='LEN',
            default=DEFAULT_MIN_PREFIXLEN[4], help=(
                'The biggest IPv4 network that still counts as a parent, '
                'as a prefix length -- 24 means a /24 or smaller '
                f'(default: {DEFAULT_MIN_PREFIXLEN[4]})'))
        parser.add_argument(
            '--min-prefixlen6', type=int, metavar='LEN',
            default=DEFAULT_MIN_PREFIXLEN[6], help=(
                'The same for IPv6. DESIGN.md only states the /24, so '
                'this default is a guess at the matching LAN size '
                f'(default: {DEFAULT_MIN_PREFIXLEN[6]})'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_min_prefixlen(args.min_prefixlen4, args.min_prefixlen6)
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._min_prefixlen = dict(DEFAULT_MIN_PREFIXLEN)

    def set_min_prefixlen(self, for_v4, for_v6):
        assert 0 <= for_v4 <= 32, for_v4
        assert 0 <= for_v6 <= 128, for_v6
        self._min_prefixlen = {4: for_v4, 6: for_v6}

    def find(self):
        return [
            IpFinding(ipaddr, note=a_note(wanted, covering))
            for ipaddr, wanted, covering in find_unparented_ips(
                get_all_prefixes(self.nbapi),
                get_all_ip_addresses(self.nbapi),
                min_prefixlen=self._min_prefixlen)]
