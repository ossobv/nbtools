"""
Check for consistent BMC interfaces.

Three things say an interface is the BMC:

- it is named BMC (--name says otherwise),
- it is flagged mgmt_only, or
- the device's oob_ip sits on it, whatever it is called.

This linter warns if:

- A device with interfaces and not device bays (chassis) does not have a
  BMC-style interface.
- A BMC-style interface does not have mgmt_only set.
- A BMC-style interface does not have a single MAC address tied to it.

The goal is to find devices that lack a BMC MAC, so we can then check
that all BMCs get an IP.
"""
from ..command import LintCommand
from ..util import in_chunks

from .findings import DeviceFinding, InterfaceFinding


# The interface a machine's management controller sits on. Configurable
# because this is a naming convention rather than a NetBox concept, but
# defaulted because it is the convention here.
BMC_NAME = 'BMC'


def oob_interfaces_by_device(nbapi, devices):
    """
    The interface each device's oob_ip sits on, keyed by device id

    A device is left out when its oob_ip is on nothing, on a VM
    interface, or on an interface belonging to some other device.
    None of those is an interface of this machine, and the device
    then counts as having no BMC -- which the note on that finding
    spells out, since "there is an oob ip but it is nowhere" is a
    different fault from "there is no oob ip".
    """
    device_of_ip = {}
    for device in devices:
        oob = device.oob_ip
        if oob is not None:
            device_of_ip[oob.id] = device.id

    by_device = {}
    for ids in in_chunks(sorted(device_of_ip)):
        for ipaddr in nbapi.ipam.ip_addresses.filter(id=ids):
            if getattr(ipaddr, 'assigned_object_type', None) != (
                    'dcim.interface'):
                continue

            iface = ipaddr.assigned_object
            device_id = device_of_ip[ipaddr.id]
            if iface is None or iface.device is None:
                continue
            if iface.device.id != device_id:
                continue

            by_device[device_id] = iface

    return by_device


def named_interfaces_by_device(nbapi, devices, name):
    """
    The interfaces of that name, keyed by device id

    name__ie is the case-insensitive exact lookup, and the match is
    made again here rather than trusted to the server. An
    inconsistently cased "bmc" can now be reported.

    A device can hold more than one, since NetBox's uniqueness is
    per exact name and "BMC" and "bmc" are two of those.
    """
    wanted = str(name).lower()

    by_device = {}
    for ids in in_chunks(sorted(device.id for device in devices)):
        for iface in nbapi.dcim.interfaces.filter(
                device_id=ids, name__ie=name):
            if str(iface.name).lower() != wanted:
                continue

            by_device.setdefault(iface.device.id, []).append(iface)

    return by_device


def mgmt_only_interfaces_by_device(nbapi, devices):
    """
    The interfaces flagged mgmt_only, keyed by device id

    NetBox's own way of saying an interface manages the machine
    rather than carrying its traffic. Whatever such an interface is
    named, it is checked as a BMC -- and not complained about for
    the name.
    """
    by_device = {}
    for ids in in_chunks(sorted(device.id for device in devices)):
        for iface in nbapi.dcim.interfaces.filter(
                device_id=ids, mgmt_only=True):
            assert iface.mgmt_only
            by_device.setdefault(iface.device.id, []).append(iface)

    return by_device


def macs_by_interface(nbapi, ifaces):
    """
    The MAC records sitting on each of these interfaces, by interface id

    assigned_object_type is checked even though interface_id already
    asks the question: a dcim.interface id and a
    virtualization.vminterface id come from different tables, so
    anything the filter lets through that is not a device interface
    is not ours.
    """
    by_iface = {}
    for ids in in_chunks(sorted(iface.id for iface in ifaces)):
        for mac in nbapi.dcim.mac_addresses.filter(interface_id=ids):
            if getattr(mac, 'assigned_object_type', None) != 'dcim.interface':
                continue

            iface = mac.assigned_object
            if iface is None:
                continue

            by_iface.setdefault(iface.id, []).append(mac)

    return by_iface


def find_bmc_interfaces(nbapi, name=BMC_NAME):
    """
    Every device and the BMC-like interfaces it holds

    Returns [(device, ifaces)] ordered by device id, the interfaces
    within a device ordered by id too. A device with no BMC-like
    interface comes back with an empty list rather than being left
    out: that is a finding of its own.
    """
    devices = sorted(nbapi.dcim.devices.all(), key=(lambda dev: dev.id))
    oob = oob_interfaces_by_device(nbapi, devices)
    named = named_interfaces_by_device(nbapi, devices, name)
    mgmt = mgmt_only_interfaces_by_device(nbapi, devices)

    found = []
    for device in devices:
        # The order matters, through the setdefault below. The first
        # two reads hand back whole interfaces; the oob one hands
        # back the brief record nested in an IP address, which has
        # no mgmt_only on it at all. So an interface that is in more
        # than one of these is kept as the version that knows the
        # flag, and only an interface known *nowhere* but the oob
        # read arrives brief -- which is exactly an interface that is
        # neither named BMC nor flagged, so nothing asks it.
        ifaces = {}
        for source in (named.get(device.id, []), mgmt.get(device.id, [])):
            for iface in source:
                ifaces.setdefault(iface.id, iface)

        oob_iface = oob.get(device.id)
        if oob_iface is not None:
            ifaces.setdefault(oob_iface.id, oob_iface)

        found.append((device, [ifaces[key] for key in sorted(ifaces)]))

    return found


def a_note(macs):
    "Say how many MACs there are and, when there are several, which"
    if not macs:
        return 'no mac address'

    detail = ', '.join(
        f'#{mac.id} {str(mac.mac_address).lower()}' for mac in macs)

    return f'{len(macs)} mac addresses: {detail}'


def is_named_bmc(iface, name):
    "Whether this interface is the BMC by name rather than by flag"
    return str(iface.name).lower() == str(name).lower()


def interface_notes(iface, macs, name):
    """
    What is wrong with this BMC interface, or an empty list

    Two separate faults, reported on one line when an interface has
    both: nothing can reach the machine, and NetBox does not know
    the interface is for reaching it OOB.

    The mgmt_only half is only asked of an interface that is the BMC
    by *name*. One that is the BMC because it holds the oob_ip is
    named whatever the vendor calls it, and this has no standing to
    say what NetBox should think of it.
    """
    notes = []

    if len(macs) != 1:
        notes.append(a_note(macs))

    if is_named_bmc(iface, name) and not iface.mgmt_only:
        notes.append('mgmt_only is not set')

    return notes


def wants_a_bmc(device):
    """
    Whether a device with no BMC is one worth reporting

    Two kinds are not, and both are read off the counts the device
    serializer already carries rather than costing a read:

    - a device with no interfaces at all. A patch panel or a PDU is
      a thing in a rack rather than a machine reached over a
      network, and NetBox holding no interfaces for it says so.
    - a device with device bays. A chassis is the enclosure; the
      BMCs belong to the blades sitting in it, and each of those is
      a device of its own that this check reaches on its own.

    A device missing either count is reported, which is the loud
    side to fail on: this is what says a machine cannot be reached.
    """
    if device.interface_count == 0:
        return False

    if device.device_bay_count:
        return False

    return True


def finding_sort_key(finding):
    """
    Group the findings by kind, then order them by what they say

    The two kinds read differently -- a machine with no BMC at all,
    and a BMC whose MAC addresses are wrong -- so a report is easier
    to work through with each kind together rather than interleaved
    device by device. Within a kind the rendered line is the order,
    and that line starts with the device name.
    """
    return (type(finding).__name__, str(finding))


def no_bmc_note(device):
    "Say whether there is no oob IP, or on a different device"
    oob = device.oob_ip
    if oob is None:
        return 'no bmc-like interface'

    return (
        f'no bmc-like interface (oob ip {oob.address} is on no '
        'interface of this device)')


class DeviceBmcsCommand(LintCommand):
    name = 'device-bmcs'
    help = (
        'Find machines whose management controller cannot be reached. A '
        'BMC is reached by its MAC before it is reached by anything '
        'else, so a BMC interface with no MAC on it cannot be found. One '
        'with two means nothing can tell which of them to use. '
        'A BMC here is an interface named BMC, one flagged mgmt_only, '
        'or the one the device oob_ip sits on; a device with none of '
        'those is reported too, as is an interface named BMC that is '
        'not flagged mgmt_only.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--name', default=BMC_NAME, metavar='NAME', help=(
            'The interface name that says an interface is the BMC '
            f'(default: {BMC_NAME}).'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_name(args.name)
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._name = BMC_NAME

    def set_name(self, name):
        assert name, name
        self._name = name

    def find(self):
        found = find_bmc_interfaces(self.nbapi, name=self._name)

        # One read for all of them, after the whole list is known.
        macs = macs_by_interface(self.nbapi, [
            iface for _device, ifaces in found for iface in ifaces])

        findings = []
        for device, ifaces in found:
            if not ifaces:
                if wants_a_bmc(device):
                    findings.append(
                        DeviceFinding(device, note=no_bmc_note(device)))
                continue

            for iface in ifaces:
                on_it = sorted(
                    macs.get(iface.id, []), key=(lambda mac: mac.id))

                notes = interface_notes(iface, on_it, self._name)
                if notes:
                    findings.append(
                        InterfaceFinding(iface, note='; '.join(notes)))

        findings.sort(key=finding_sort_key)

        return findings
