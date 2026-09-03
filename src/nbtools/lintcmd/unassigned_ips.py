from ..command import LintCommand
from ..netbox import get_unassigned_ip_addresses

from .findings import IpFinding
from .statusarg import StatusArgument


# The families --family takes. Spelled as the strings NetBox uses in
# the query, converted to int for the filter.
FAMILIES = ('4', '6')

# The --status flag: which addresses get reported.
#
# Reserved is the one left out by default. DHCP and SLAAC are not
# left out: unused/detached IPs previously handed out by DHCP are
# among those findings we're looking for.
STATUS = StatusArgument(
    'addresses', ('active', 'reserved', 'deprecated', 'dhcp', 'slaac'),
    skipped_by_default=('reserved',),
    reason=(
        'a reserved address is one held on purpose with nothing on it, '
        'so sitting on no interface is its normal state'))


class UnassignedIpsCommand(LintCommand):
    name = 'unassigned-ips'
    help = (
        'Find IP addresses that sit on no interface. An address nothing '
        'holds is either a leftover from a machine that went away or a '
        'reservation nobody wrote down, and either way it is what the '
        'periodic IPAM sweep is looking for. Reserved addresses are '
        'skipped -- those are held on purpose with nothing on them. '
        'Pass --status=all to see them anyway.')

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
        Report only addresses with these statuses, 'all' for every one.

        Nothing, or an empty list, leaves the default in place: every
        status but the reserved.
        """
        self._statuses = STATUS.filter_for(statuses)

    def find(self):
        family = (int(self._family) if self._family else None)

        # The status is sifted here rather than in the query, unlike
        # the family. The read is already down to the unassigned
        # addresses, so there is next to nothing left to save, and the
        # default is "every status except one" -- which NetBox can
        # only be asked for through the __n negation this code has
        # never had a real install to try it against.
        return [
            IpFinding(ipaddr)
            for ipaddr in get_unassigned_ip_addresses(
                self.nbapi, family=family)
            if self._statuses.allows(ipaddr)]
