from ..command import LintCommand
from ..ipam import address_of, find_in_multiple_vrfs, network_of
from ..netbox import get_all_ip_addresses, get_all_prefixes
from .findings import InMultipleVrfsFinding


# The families --family takes. Spelled as the strings NetBox uses in
# the query, converted to int for the filter.
FAMILIES = ('4', '6')


class BaseInMultipleVrfsCommand(LintCommand):
    """
    Shared by duplicate-prefixes and duplicate-ips.

    The assumption is that all VRFs have unique IPs. If we find the same
    IP or prefix in multiple VRFs, we flag the anomaly.
    """
    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--family', choices=FAMILIES, help=(
            'Report only this address family. Both, by default.'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_family(args.family)
        return cmd

    @staticmethod
    def value_of(record):
        "The value two records have to share to be a duplicate"
        raise NotImplementedError

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._family = None

    def set_family(self, family):
        assert family in FAMILIES or family is None, family
        self._family = family

    def get_records(self, nbapi):
        "Read the table this command checks"
        raise NotImplementedError

    def find(self):
        return [
            InMultipleVrfsFinding(value, records)
            for value, records in find_in_multiple_vrfs(
                self.get_records(self.nbapi), self.value_of)]


class DuplicatePrefixesCommand(BaseInMultipleVrfsCommand):
    name = 'duplicate-prefixes'
    help = (
        'Find prefixes that exist in more than one VRF. '
        'The assumption is that IP space is unique and does not exist '
        'in multiple VRFs.')

    @staticmethod
    def value_of(record):
        # By the network rather than by the recorded string, so that
        # 10.0.0.0/24 and a 10.0.0.1/24 typed off its boundary are one
        # prefix, which is what they are.
        return network_of(record)

    def get_records(self, nbapi):
        return get_all_prefixes(nbapi, family=self._family)


class DuplicateIpsCommand(BaseInMultipleVrfsCommand):
    name = 'duplicate-ips'
    help = (
        'Find IP addresses that exist in more than one VRF. '
        'The assumption is that IP space is unique and does not exist '
        'in multiple VRFs.')

    @staticmethod
    def value_of(record):
        # The bare address, mask dropped: 10.0.0.1/24 in one VRF and
        # 10.0.0.1/31 in another are the same address twice, and the
        # differing mask is a different problem.
        return address_of(record)

    def get_records(self, nbapi):
        return get_all_ip_addresses(nbapi, family=self._family)
