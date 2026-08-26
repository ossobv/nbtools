from ..command import LintCommand
from ..ipam import address_of, find_in_multiple_vrfs, network_of
from ..netbox import get_all_ip_addresses, get_all_prefixes
from .findings import MultipleVrfsFinding


class BaseMultipleVrfsCommand(LintCommand):
    """
    Shared by duplicate-prefixes and duplicate-ips.

    Every VRF in this setup holds its own addresses, so the same value
    routed in two of them is an anomaly. The two commands are the same
    check over two tables, kept apart because the values they print
    are different -- a prefix is not an address, and a --porcelain run
    of both would be a stream nothing could tell apart.
    """
    @classmethod
    def get_records(cls, nbapi):
        "Read the table this command checks"
        raise NotImplementedError

    @staticmethod
    def value_of(record):
        "The value two records have to share to be a duplicate"
        raise NotImplementedError

    def find(self):
        return [
            MultipleVrfsFinding(value, records)
            for value, records in find_in_multiple_vrfs(
                self.get_records(self.nbapi), self.value_of)]


class DuplicatePrefixesCommand(BaseMultipleVrfsCommand):
    name = 'duplicate-prefixes'
    help = (
        'Find prefixes that exist in more than one VRF. Every VRF here '
        'holds its own addresses, so the same prefix in two of them is '
        'either a leak between the two or a copy-paste.')

    @classmethod
    def get_records(cls, nbapi):
        return get_all_prefixes(nbapi)

    @staticmethod
    def value_of(record):
        # By the network rather than by the recorded string, so that
        # 10.0.0.0/24 and a 10.0.0.1/24 typed off its boundary are one
        # prefix, which is what they are.
        return network_of(record)


class DuplicateIpsCommand(BaseMultipleVrfsCommand):
    name = 'duplicate-ips'
    help = (
        'Find IP addresses that exist in more than one VRF. Same rule as '
        'duplicate-prefixes: one address belongs to one VRF here.')

    @classmethod
    def get_records(cls, nbapi):
        return get_all_ip_addresses(nbapi)

    @staticmethod
    def value_of(record):
        # The bare address, mask dropped: 10.0.0.1/24 in one VRF and
        # 10.0.0.1/31 in another are the same address twice, and the
        # differing mask is a second problem rather than an excuse.
        return address_of(record)
