"""
The address arithmetic the IPAM lint commands do.

When looking for empty prefixes, the cheapest way is to fetch all
records, sort them and check for containment.
"""
from bisect import bisect_left
from ipaddress import ip_interface, ip_network


# What the absence of a VRF is called in a listing. NetBox leaves the
# field empty for the global routing table; "global" reads better in a
# column of VRF names than a blank does.
GLOBAL_VRF = 'global'

# The longest mask there is, per address family. A prefix that long
# holds exactly one address.
HOST_PREFIXLEN = {4: 32, 6: 128}


def vrf_id(record):
    "The id of the VRF a prefix or address is routed in, or None"
    vrf = getattr(record, 'vrf', None)
    return (vrf.id if vrf is not None else None)


def vrf_name(record):
    "The name of that VRF, or 'global' for the table with no VRF"
    vrf = getattr(record, 'vrf', None)
    return (str(vrf.name) if vrf is not None else GLOBAL_VRF)


def status_name(record):
    """
    The status of a record as a bare word, e.g. 'active'

    A pynetbox choice field is an object with .value and .label. The
    listings want the value: 'container' is what the operator filters
    on in the UI, 'Container' is not.
    """
    status = getattr(record, 'status', None)
    if status is None:
        return '-'

    return str(getattr(status, 'value', status))


def network_of(prefix):
    """
    The ip_network of an ipam.prefix record

    strict=False on purpose: NetBox stores what it was given, so a
    prefix recorded as 10.0.0.1/24 exists and has to be readable. It
    normalises to 10.0.0.0/24 here, which is the network the operator
    meant.
    """
    return ip_network(str(prefix.prefix), strict=False)


def address_of(ipaddr):
    "The bare address of an ipam.ip_address, mask dropped"
    return ip_interface(str(ipaddr.address)).ip


def prefixlen_of(ipaddr):
    "The mask an ipam.ip_address was recorded with"
    return ip_interface(str(ipaddr.address)).network.prefixlen


def _network_key(net):
    "Sort networks so that the contents of one are a contiguous run"
    return (net.version, int(net.network_address), net.prefixlen)


def sort_key(value):
    """
    Order a network or a bare address, across families

    int('::') and int('0.0.0.0') are both 0, so the family has to come
    first or the two families interleave. Networks and addresses both
    go through here so that a caller holding either can sort it.
    """
    if hasattr(value, 'network_address'):
        return _network_key(value)

    return _address_key(value)


def prefix_sort_key(prefix):
    "Sort ipam.prefix records into reading order: v4 first, then by network"
    return _network_key(network_of(prefix))


def address_sort_key(ipaddr):
    "Sort ipam.ip_address records into reading order"
    return _address_key(address_of(ipaddr))


def _address_key(addr):
    return (addr.version, int(addr))


class VrfIndex:
    """
    The prefixes and addresses of one VRF, indexed for containment.

    Two indexes, because the two questions want different shapes:

    - Networks are sorted. Sorting by (family, network address, mask)
      puts everything inside a prefix directly after it, so "is
      anything inside this one" is a binary search plus a look at the
      neighbour rather than a scan of the table.
    - Addresses are sorted too, and searched by range, for the same
      reason.
    - Networks are *also* kept in a set, for the other direction. To
      ask which prefixes contain an address, walk the masks and look
      each candidate supernet up: 9 hashed lookups to cover /32 to
      /24, against a scan of every prefix in the VRF.
    """
    def __init__(self):
        self._networks = []
        self._addresses = []
        self._network_set = set()
        self._network_keys = None
        self._address_keys = None

    def add_prefix(self, network):
        self._networks.append(network)
        self._network_set.add(network)
        self._network_keys = None

    def add_address(self, address):
        self._addresses.append(address)
        self._address_keys = None

    def _sort(self):
        """
        Sort both lists and keep the keys bisect searches against.

        The keys are held rather than rebuilt per call: there is one
        of these questions asked per record, so rebuilding would make
        a linear index into a quadratic one.
        """
        if self._network_keys is None:
            self._networks.sort(key=_network_key)
            self._network_keys = [
                _network_key(net) for net in self._networks]

        if self._address_keys is None:
            self._addresses.sort(key=_address_key)
            self._address_keys = [
                _address_key(addr) for addr in self._addresses]

    def has_child_prefix(self, network):
        """
        True when a smaller prefix sits inside this one.

        Strictly smaller: the same prefix recorded twice is a
        duplicate, which should be reported by a lint command.
        """
        self._sort()

        first = bisect_left(
            self._network_keys,
            (network.version, int(network.network_address), 0))

        for other in self._networks[first:]:
            if other.version != network.version:
                break
            if other.network_address > network.broadcast_address:
                break
            if other.prefixlen > network.prefixlen:
                return True

        return False

    def has_address_in(self, network):
        "True when this prefix holds at least one recorded address"
        self._sort()

        keys = self._address_keys
        first = bisect_left(
            keys, (network.version, int(network.network_address)))
        if first >= len(keys):
            return False

        version, value = keys[first]

        return (
            version == network.version
            and value <= int(network.broadcast_address))

    def covering_prefixlens(self, address, down_to=0):
        """
        The masks of the prefixes that contain this address.

        Longest first, and it stops at down_to: a caller asking
        whether anything as small as a /24 covers the address has no
        use for the /8 that also does.
        """
        found = []
        for prefixlen in range(
                HOST_PREFIXLEN[address.version], down_to - 1, -1):
            candidate = ip_network(f'{address}/{prefixlen}', strict=False)
            if candidate in self._network_set:
                found.append(prefixlen)

        return found


class IpamIndex:
    """
    Every prefix and address, grouped by VRF and indexed.

    VRFs are kept apart because a prefix in one says nothing about an
    address in another. The checks that deliberately look *across*
    VRFs -- duplicate-prefixes, duplicate-ips -- do their own grouping
    and do not come through here.
    """
    def __init__(self, prefixes=(), addresses=()):
        self._by_vrf = {}

        for prefix in prefixes:
            self._vrf(vrf_id(prefix)).add_prefix(network_of(prefix))

        for ipaddr in addresses:
            self._vrf(vrf_id(ipaddr)).add_address(address_of(ipaddr))

    def _vrf(self, id_):
        try:
            return self._by_vrf[id_]
        except KeyError:
            index = self._by_vrf[id_] = VrfIndex()
            return index

    def is_empty_prefix(self, prefix):
        "True when nothing in this VRF sits inside this prefix"
        index = self._by_vrf.get(vrf_id(prefix))
        if index is None:
            return True

        network = network_of(prefix)

        return not (
            index.has_child_prefix(network)
            or index.has_address_in(network))

    def covering_prefixlens(self, ipaddr, down_to=0):
        "The masks of the prefixes covering this address, longest first"
        index = self._by_vrf.get(vrf_id(ipaddr))
        if index is None:
            return []

        return index.covering_prefixlens(address_of(ipaddr), down_to=down_to)


def find_in_multiple_vrfs(records, value_of):
    """
    The values that exist in more than one VRF

    Returns [(value, records)] in reading order, records by id. "All
    VRFs have unique IPs in our setup" is the rule this checks: a
    value routed in two of them is either a leak or a copy-paste, and
    either way nothing downstream can tell which one it meant.

    More than one VRF, not more than one record: the same address
    twice inside one VRF is what an anycast gateway looks like, and
    clone-interface creates those on purpose.
    """
    by_value = {}
    for record in records:
        by_value.setdefault(value_of(record), []).append(record)

    groups = []
    for value, found in by_value.items():
        if len({vrf_id(record) for record in found}) < 2:
            continue

        groups.append(
            (value, sorted(found, key=(lambda record: record.id))))

    return sorted(groups, key=(lambda group: sort_key(group[0])))
