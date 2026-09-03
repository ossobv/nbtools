from ipaddress import ip_interface
from re import compile as re_compile


# The prefix length that makes a subnet a point-to-point link, per
# address family. A /31 (RFC 3021) and a /127 (RFC 6164) hold two
# addresses and neither a network nor a broadcast address, so "the
# other one" is unambiguous.
POINT_TO_POINT_PREFIXLEN = {4: 31, 6: 127}


def natsort_key(name: str) -> tuple[str | int]:
    return tuple(
        (int(i) if i.isdigit() else i)
        for i in natsort_key.re.split(name)
        if i)
natsort_key.re = re_compile(r'(\d+)')  # noqa


def split_subinterface(name):
    """
    Split 'swp1.2107' into ('swp1', 2107), or return None

    Base-10 numeric suffixes only. 'swp1.foo' is a name that happens
    to hold a dot, not a subinterface, and 'swp1' is not one either.
    That restriction is deliberate: the number is the VLAN or VRF tag
    the switch config generates, and a non-numeric suffix does not
    carry one.
    """
    match = split_subinterface.re.match(str(name))
    if not match:
        return None

    return (match.group('parent'), int(match.group('number')))
split_subinterface.re = re_compile(  # noqa
    r'^(?P<parent>.+)\.(?P<number>[0-9]+)$')


def mac_from_interface_name(name):
    """
    The MAC address a udev-generated interface name encodes, or None

    systemd's predictable naming gives a NIC with no stable bus path a
    name built out of its own MAC: 'enxbe3af2b6059f' is
    be:3a:f2:b6:05:9f, and 'wlx...' is the wireless spelling of the
    same thing. The name is therefore *derived* from the address, not
    recorded next to it -- which is what makes it worth reading back.

    Returns the address lower case and colon separated, so it compares
    against a NetBox mac_address directly.
    """
    match = mac_from_interface_name.re.match(str(name).lower())
    if not match:
        return None

    hexes = match.group('mac')

    return ':'.join(hexes[i:i + 2] for i in range(0, 12, 2))
mac_from_interface_name.re = re_compile(  # noqa
    r'^(?:en|wl)x(?P<mac>[0-9a-f]{12})$')


def quoted_name(name) -> str:
    """
    Single-quote a name if it needs it, doubling quotes like SQL does

    NetBox device names are free-form, so this is a real one:

        FREE (was-planned: node3.zl.backend1.prod.juno.cloud)

    Unquoted, the "device:interface rest of the line" output cannot be
    read: the device name runs into the rest of the sentence. So a name
    holding a space gets quoted, and an embedded quote is doubled:

        Bob's spare (old)  ->  'Bob''s spare (old)'
    """
    name = str(name)
    if ' ' in name or "'" in name:
        return "'{}'".format(name.replace("'", "''"))

    return name


def peer_address(address):
    """
    The other address of a point-to-point link

    Takes 10.0.0.1/31 and returns 10.0.0.0/31, and the other way
    around. A VM sits on one end of such a link and its gateway on the
    other, so this is how migrate-gateway finds a gateway: by arithmetic,
    without asking NetBox which addresses are related.

    Raises ValueError for anything that is not a /31 or a /127, because
    on a larger subnet "the other address" does not mean anything.
    """
    ip = ip_interface(str(address))
    wanted = POINT_TO_POINT_PREFIXLEN[ip.version]
    if ip.network.prefixlen != wanted:
        raise ValueError(
            f'{address} is not a point-to-point address: expected '
            f'/{wanted}, got /{ip.network.prefixlen}')

    first, second = ip.network[0], ip.network[1]
    other = (second if ip.ip == first else first)

    return ip_interface(f'{other}/{wanted}')
