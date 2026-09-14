"""
Find the interfaces that no cable is plugged into.

The other half of unattached-cables: that one finds a cable with an end
missing, this one finds a port with no cable at all. Most uncabled ports
are simply unused, so the report is narrowed to the ones that look in
use. Left alone are:

- a disabled interface, which is NetBox's own way of saying unused;
- one marked connected, which is NetBox's way of saying the link exists
  but is not modelled as a cable;
- a virtual, bridge, LAG or wireless interface, since NetBox refuses a
  cable on those;
- a subinterface, which is cabled through its parent;
- the loopback, by name;
- an interface whose name matches --exclude, such as a BMC port or an
  enx* USB NIC that is never cabled on purpose;
- an interface with no IP address, unless --no-require-ip. An address
  on one of its subinterfaces or on its LAG counts: on a routed port
  the addresses live there, and it is the port that takes the cable.
"""
from argparse import ArgumentTypeError
from fnmatch import fnmatchcase

from pynetbox import RequestError

from ..command import LintCommand
from ..exceptions import ApiError
from ..util import in_chunks, split_subinterface

from .findings import InterfaceFinding


# Interface names that are never cabled, whatever their type says. A
# loopback typed virtual is already left out by its type; this is for
# the one that was imported as something else.
SKIPPED_NAMES = ('lo',)

# The interface types NetBox refuses a cable on, its
# NONCONNECTABLE_IFACE_TYPES. The kind=physical filter leaves these out
# server-side; they are named here to ask again.
VIRTUAL_TYPES = ('virtual', 'bridge', 'lag')
WIRELESS_TYPE_PREFIXES = ('ieee802.11', 'ieee802.15', 'other-wireless')

# What narrows an interface listing to the ports this is about.
# wants_a_cable() asks every one of them again.
PORT_FILTERS = {
    'cabled': False, 'enabled': True, 'kind': 'physical',
    'mark_connected': False}


def type_of(iface):
    "The interface type as a bare word, or '' when it has none"
    kind = getattr(iface, 'type', None)
    if kind is None:
        return ''

    return str(getattr(kind, 'value', kind))


def takes_a_cable(iface):
    "Whether NetBox would let a cable be plugged into this interface"
    kind = type_of(iface)

    return not (
        kind in VIRTUAL_TYPES or kind.startswith(WIRELESS_TYPE_PREFIXES))


def is_subinterface(iface):
    """
    Whether this is a subinterface, by its parent or by its name

    Either one says so. subinterface-parents is where the two
    disagreeing gets reported; here it only matters that neither kind
    is a port.
    """
    if getattr(iface, 'parent', None) is not None:
        return True

    return split_subinterface(iface.name) is not None


def wants_a_cable(iface):
    """
    Whether this interface, lacking a cable, is worth reporting

    The IP half is not asked here; that one needs a read.

    find() already asks NetBox for most of this through the filters, and
    it is asked again here all the same: NetBox ignores a filter it does
    not know, and the answer would then be every interface there is,
    reported as uncabled. That would be loud, and wrong in a way that
    looks like data.
    """
    if getattr(iface, 'cable', None) is not None:
        return False

    if getattr(iface, 'mark_connected', False):
        return False

    if not getattr(iface, 'enabled', True):
        return False

    if not takes_a_cable(iface):
        return False

    if is_subinterface(iface):
        return False

    return str(iface.name) not in SKIPPED_NAMES


def parse_patterns(value):
    "One --exclude value: a name or a glob, or several comma separated"
    patterns = [word.strip() for word in value.split(',')]
    if not all(patterns):
        raise ArgumentTypeError(f'{value!r}: empty interface name')

    return patterns


def is_excluded(iface, patterns):
    """
    Whether this interface's name matches one of these glob patterns

    Only the name is matched, not DEV:IFACE, and case-sensitively, the
    way NetBox names are: BMC does not leave out bmc.
    """
    name = str(iface.name)

    return any(fnmatchcase(name, pattern) for pattern in patterns)


def holder_key(iface):
    """
    The (device id, name) an address on this interface counts for

    An address on swp1.1234 counts for swp1. This reads only the id
    and the name, so the brief interface record NetBox nests in an IP
    address will do.
    """
    split = split_subinterface(iface.name)
    name = (split[0] if split else iface.name)

    return (iface.device.id, str(name))


def addresses_by_holder(nbapi):
    """
    The IP addresses on device interfaces, keyed by holder_key

    One listing of the address table: this runs before any interface
    is read, so there is no device list to narrow it by, and nearly
    every device holds an address anyway.
    """
    # Fetch the ContentType object for 'dcim.interface'
    try:
        # NetBox 4.5+
        # BUG/TODO: We're retrying this automatically before failing.
        ct = nbapi.core.object_types.get(app_label='dcim', model='interface')
    except RequestError:
        # NetBox 4.0 - 4.4
        ct = nbapi.extras.object_types.get(app_label='dcim', model='interface')

    by_holder = {}

    # We cannot do interface__empty=False or vminterface__empty=True here,
    # so we need the assigned_object_type (content type).
    for ipaddr in nbapi.ipam.ip_addresses.filter(assigned_object_type=ct.id):
        assert ipaddr.assigned_object is not None, (
            ipaddr, ipaddr.assigned_object, ipaddr)
        assert ipaddr.assigned_object_type == 'dcim.interface', (
            ipaddr, ipaddr.assigned_object_type, ipaddr)

        iface = ipaddr.assigned_object
        assert iface and iface.device, (ipaddr, iface)

        by_holder.setdefault(holder_key(iface), []).append(ipaddr)

    return by_holder


def interfaces_by_key(nbapi, keys, **filters):
    """
    The interfaces whose (device id, name) is one of these keys

    NetBox cannot filter on the pair, so each chunk asks for its
    devices and its names apart and gets the cross product back: with
    leaf1:swp1 and leaf2:swp2 asked for, leaf1:swp2 comes too. Those
    are dropped here, which also keeps this right when NetBox ignores
    the name filter.
    """
    keys = set(keys)
    found = []
    for chunk in in_chunks(sorted(keys)):
        for iface in nbapi.dcim.interfaces.filter(
                device_id=sorted({key[0] for key in chunk}),
                name=sorted({key[1] for key in chunk}), **filters):
            if (iface.device.id, str(iface.name)) in keys:
                found.append(iface)

    return found


def ports_holding_addresses(nbapi, by_holder):
    """
    The uncabled ports that hold an address, or whose LAG does

    Asked for by name rather than by listing every uncabled port: most
    of those are unused, hold nothing, and were the cost of this
    command. A LAG member's name is not known from any address, so the
    LAGs are read by name first and their members by lag_id.
    """
    ports = {
        iface.id: iface
        for iface in interfaces_by_key(nbapi, by_holder, **PORT_FILTERS)}

    lag_ids = sorted(
        iface.id for iface in interfaces_by_key(nbapi, by_holder, type='lag')
        if type_of(iface) == 'lag')
    for ids in in_chunks(lag_ids):
        for iface in nbapi.dcim.interfaces.filter(lag_id=ids, **PORT_FILTERS):
            ports[iface.id] = iface

    return list(ports.values())


def addresses_of(iface, by_holder):
    """
    The addresses this interface counts as having, ordered by id

    Its own and its subinterfaces', and those of the LAG it is a member
    of along with the LAG's subinterfaces. A LAG member carries no
    address of its own, but it is the member that takes the cable.
    """
    found = list(by_holder.get(holder_key(iface), []))

    lag = getattr(iface, 'lag', None)
    if lag is not None:
        found.extend(by_holder.get((iface.device.id, str(lag.name)), []))

    return sorted(found, key=(lambda ipaddr: ipaddr.id))


def a_note(iface, addresses):
    """
    The type, and the first address along with where it sits

    The type is there because it is what an exclusion would be written
    against. The address is there because it is what makes the port look
    in use, and when it sits on a subinterface or a LAG, it is the one
    that answers "why is this reported".
    """
    if not addresses:
        return ''

    first = addresses[0]
    note = f'ip={first.address}'
    if len(addresses) > 1:
        note += f' (+{len(addresses) - 1} more)'

    return note


class UnattachedInterfacesCommand(LintCommand):
    name = 'unattached-interfaces'
    help = (
        'Find interfaces that no cable is plugged into; the other half of '
        'unattached-cables. Only ports that look in use are reported. '
        'Disabled, marked-connected, virtual, LAG, bridge and wireless '
        'interfaces are left alone, and so are subinterfaces, lo and the '
        'names given to --exclude. So is an interface with no IP address, '
        'unless --no-require-ip. An address on its subinterfaces or its '
        'LAG counts.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument(
            '--require-ip', dest='require_ip', action='store_true',
            default=True, help=(
                'Report only interfaces holding an IP address, directly or '
                'through a subinterface or LAG. This is the default, and it '
                'limits the report to L3 ports.'))
        parser.add_argument(
            '--no-require-ip', dest='require_ip', action='store_false',
            help='Report uncabled interfaces with no IP address as well.')
        parser.add_argument(
            '--exclude', action='append', type=parse_patterns,
            metavar='NAME', help=(
                'Leave out interfaces with this name. Shell-style wildcards '
                'match, so quote them: --exclude="enx*". Matched against '
                'the interface name only, case-sensitively. Repeatable, or '
                'comma separated.'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_require_ip(args.require_ip)
        cmd.set_excludes(
            pattern for value in (args.exclude or ()) for pattern in value)
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._require_ip = True
        self._excludes = ()

    def set_require_ip(self, require_ip=True):
        self._require_ip = bool(require_ip)

    def set_excludes(self, patterns=()):
        self._excludes = tuple(patterns)

    def find(self):
        # With the IP requirement the addresses come first, and only the
        # ports they point at are read. Without it every uncabled port
        # is a candidate, and the addresses are not read at all: the
        # note loses them, which is cheaper than reading the address
        # table for a note.
        if self._require_ip:
            by_holder = addresses_by_holder(self.nbapi)
            ifaces = ports_holding_addresses(self.nbapi, by_holder)
        else:
            by_holder = {}
            ifaces = self.nbapi.dcim.interfaces.filter(**PORT_FILTERS)

        findings = []
        for iface in ifaces:
            if not wants_a_cable(iface):
                continue

            if is_excluded(iface, self._excludes):
                continue

            addresses = addresses_of(iface, by_holder)
            if self._require_ip and not addresses:
                continue

            findings.append(
                InterfaceFinding(iface, note=a_note(iface, addresses)))

        findings.sort(key=(lambda finding: (finding.value, finding.iface.id)))

        return findings
