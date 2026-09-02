from collections import namedtuple
from ipaddress import IPv4Interface, ip_network


__all__ = (
    'DevIface', 'Hostname', 'IPv4AddrWithMask', 'MacAddr', 'VrfPrefix')


IPv4AddrWithMask = IPv4Interface


class DevIface(namedtuple('DevIface', 'device interface')):
    """
    Takes 'leaf1:eth0', holds device='leaf1', interface='eth0'

    Split on the *last* colon: device names are free-form and do hold
    colons, e.g. 'FREE (was-planned: node3.example.com):BMC'. Interface
    names do not.

    DevIface.NONE is the interface that records assigned to nothing sit
    on. It is spelled ':' -- an empty device and an empty interface --
    and renders back as ':' in the work listing.
    """
    def __new__(cls, dev_iface_str):
        try:
            device, interface = dev_iface_str.rsplit(':', 1)
        except ValueError as e:
            raise ValueError('argument must be DEV:IFACE') from e

        return super().__new__(cls, device, interface)

    def __str__(self):
        return f'{self.device}:{self.interface}'

DevIface.NONE = DevIface(':')


class Hostname(str):
    """
    A host name as typed on the command line, e.g. 'vm1.example.com'

    Thin on purpose. It is a str, so it goes into an API filter and
    into the recorder unchanged; what it adds is a place for argparse
    to reject the obviously wrong, and a name in --help that says what
    the argument is.
    """
    def __new__(cls, name):
        if not name or any(ch.isspace() for ch in name):
            raise ValueError(f'{name!r} does not look like a host name')

        return super().__new__(cls, name)


class VrfPrefix(namedtuple('VrfPrefix', 'prefix vrf')):
    """
    Takes '10.1.2.0/24@vrf-red', holds prefix and vrf='vrf-red'

    One token on purpose. A prefix on its own does not name a record
    -- NetBox lets the same prefix exist in several VRFs, which is
    what nblint duplicate-prefixes is about -- and the nblint pipeline
    is "--porcelain | xargs", where xargs hands over one argument per
    line. So both halves have to fit in one word.

    Split on the *first* '@': a prefix never holds one and a VRF name
    might. No '@' at all, or nothing after it, is the global routing
    table, so '10.1.2.0/24' and '10.1.2.0/24@' are the same thing --
    the empty half spelling the absent one, as DevIface.NONE does.

    The prefix is normalised. NetBox stores what it was given, so
    10.1.2.1/24 is a prefix that exists; it names the same record as
    10.1.2.0/24 and this renders it that way.
    """
    def __new__(cls, vrf_prefix_str):
        prefix, _at, vrf = str(vrf_prefix_str).partition('@')
        try:
            network = ip_network(prefix, strict=False)
        except ValueError as e:
            raise ValueError(
                f'{prefix!r} is not a prefix: expected PREFIX@VRF') from e

        return super().__new__(cls, network, vrf)

    def __str__(self):
        return f'{self.prefix}@{self.vrf}'


class MacAddr:
    @staticmethod
    def parse(mac):
        mac = mac.lower()
        if ':' in mac:
            parts = mac.split(':')  # 01:23:45:67:89:ab
            if len(parts) != 6:
                return None
            joined = ''.join(parts)
        elif '.' in mac:
            parts = mac.split('.')  # 0123.4567.89ab
            if len(parts) != 3:
                return None
            joined = ''.join(parts)
        else:
            return None

        if len(joined) != 12 or any(
                ch not in '0123456789abcdef' for ch in joined):
            return None

        return ':'.join(joined[i:i+2] for i in range(0, 12, 2))

    def __init__(self, mac_str):
        parsed = self.parse(mac_str)
        if parsed is None:
            raise ValueError(f'{mac_str!r} does not look like a valid MAC')

        self._value = parsed

    def __str__(self):
        return self._value
