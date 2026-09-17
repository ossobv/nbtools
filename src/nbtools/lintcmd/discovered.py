from ..command import LintCommand
from ..exceptions import StartupError
from ..util import quoted_name


# The name the discovery runs file what they found under. A name rather
# than an id, because the id differs per NetBox install.
#
# It is not one place, though. A virtual machine has to be in a
# cluster, so that is where discovery puts one. A device has no such
# obligation: it lands in the site by this name, or gets a device type
# from the manufacturer by this name when discovery could not tell who
# made it -- or both. A hypervisor may also sit in the cluster.
DISCOVERY_NAME = 'Discovery'

# What --limit takes, for a --porcelain run that has to print one kind
# of name. Devices and virtual machines are different tables, so a
# stream holding both is one the reader cannot tell apart.
LIMIT_DEVICES = 'devices'
LIMIT_VMS = 'vms'
LIMITS = (LIMIT_DEVICES, LIMIT_VMS)


class DiscoveredFinding:
    "One device or virtual machine that a discovery run filed"

    def __init__(self, kind, record, places):
        self.kind = kind
        self.record = record
        # ('site', site), ('manufacturer', manufacturer), ...
        self.places = places

    def porcelain(self):
        return str(self.record.name)

    def __str__(self):
        places = ', '.join(
            f'{what} {quoted_name(place.name)}'
            for what, place in self.places)

        return (
            f'{self.kind} {quoted_name(self.record.name)} '
            f'#{self.record.id} filed under {places}')


class DiscoveredItemsCommand(LintCommand):
    name = 'discovered-items'
    help = (
        'List the devices and virtual machines that auto-discovery filed '
        f'under "{DISCOVERY_NAME}".\n'
        '\n'
        'A virtual machine is filed by its cluster, a device by its site '
        'or its manufacturer. Items found here are not broken, but simply '
        'not placed by hand yet. That makes them worth a periodic look.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument(
            '--name', default=DISCOVERY_NAME, metavar='NAME', help=(
                'The site, cluster and manufacturer name discovery files '
                'under, matched ignoring case '
                f'(default: {DISCOVERY_NAME})'))
        parser.add_argument('--limit', choices=LIMITS, help=(
            'Report only one kind. Required with --porcelain: a device '
            'name and a VM name come from different tables, so a stream '
            'holding both is one the reader cannot tell apart.'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_name(args.name)
        cmd.set_limit(args.limit)
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._name = DISCOVERY_NAME
        self._limit = None

    def set_name(self, name):
        assert name, name
        self._name = name

    def set_limit(self, limit):
        assert limit in LIMITS or limit is None, limit
        self._limit = limit

    def set_porcelain(self):
        if self._limit is None:
            raise StartupError(
                f'--porcelain needs --limit ({", ".join(LIMITS)}) for '
                f'{self.name}: device and VM names cannot share a stream')

        super().set_porcelain()

    def _wanted(self, limit):
        return self._limit in (None, limit)

    def _named(self, endpoint):
        "The records on this endpoint whose name is the discovery name"
        return list(endpoint.filter(name__ie=self._name))

    def _find_devices(self):
        """
        The devices in the site, the cluster or of the manufacturer

        A device can be in more than one of them, and is listed once,
        naming each.
        """
        places = (
            ('site', 'site_id', self._named(self.nbapi.dcim.sites)),
            ('cluster', 'cluster_id',
             self._named(self.nbapi.virtualization.clusters)),
            ('manufacturer', 'manufacturer_id',
             self._named(self.nbapi.dcim.manufacturers)),
        )

        found = {}
        for what, key, records in places:
            for place in records:
                for device in self.nbapi.dcim.devices.filter(
                        **{key: place.id}):
                    found.setdefault(device.id, (device, []))[1].append(
                        (what, place))

        return [
            DiscoveredFinding('device', device, device_places)
            for device, device_places in found.values()]

    def _find_vms(self):
        return [
            DiscoveredFinding('virtual-machine', vm, [('cluster', cluster)])
            for cluster in self._named(self.nbapi.virtualization.clusters)
            for vm in self.nbapi.virtualization.virtual_machines.filter(
                cluster_id=cluster.id)]

    def find(self):
        findings = []
        if self._wanted(LIMIT_DEVICES):
            findings.extend(self._find_devices())
        if self._wanted(LIMIT_VMS):
            findings.extend(self._find_vms())

        return findings
