from ..command import LintCommand
from ..util import quoted_name


# The cluster the discovery runs file what they found under. A name
# rather than an id, because the id differs per NetBox install --
# DESIGN.md's is 42 -- and the name does not.
DISCOVERY_CLUSTER = 'Discovery'

# What --limit takes, for a --porcelain run that has to print one kind
# of name. Devices and virtual machines are different tables, so a
# stream holding both is one the reader cannot tell apart.
LIMIT_DEVICES = 'devices'
LIMIT_VMS = 'vms'
LIMITS = (LIMIT_DEVICES, LIMIT_VMS)


def get_clusters(nbapi, name):
    """
    The clusters whose name matches

    q= is a freeform search, so the match is redone here rather than
    trusted to the server -- the same thing get_mac_addresses() does,
    and for the same reason.
    """
    wanted = name.lower()

    return [
        cluster for cluster in nbapi.virtualization.clusters.filter(q=name)
        if wanted in str(cluster.name).lower()]


class DiscoveredFinding:
    "One device or virtual machine that a discovery run filed"

    def __init__(self, kind, record, cluster):
        self.kind = kind
        self.record = record
        self.cluster = cluster

    def porcelain(self):
        return str(self.record.name)

    def __str__(self):
        return (
            f'{self.kind} {quoted_name(self.record.name)} '
            f'#{self.record.id} in cluster {quoted_name(self.cluster.name)}')


class DiscoveredItemsCommand(LintCommand):
    name = 'discovered-items'
    help = (
        'List the devices and virtual machines that auto-discovery filed '
        'under the Discovery cluster. Nothing here is broken as such: '
        'they are the things nobody has placed by hand yet, which is what '
        'makes them worth a periodic look.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument(
            '--cluster', default=DISCOVERY_CLUSTER, metavar='NAME', help=(
                'The cluster discovery files under, matched as a substring '
                f'(default: {DISCOVERY_CLUSTER})'))
        parser.add_argument('--limit', choices=LIMITS, help=(
            'Report only one kind. A --porcelain run wants this: a device '
            'name and a VM name come from different tables, so a stream '
            'holding both is one the reader cannot tell apart.'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_cluster(args.cluster)
        cmd.set_limit(args.limit)
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._cluster = DISCOVERY_CLUSTER
        self._limit = None

    def set_cluster(self, name):
        assert name, name
        self._cluster = name

    def set_limit(self, limit):
        assert limit in LIMITS or limit is None, limit
        self._limit = limit

    def _wanted(self, limit):
        return self._limit in (None, limit)

    def find(self):
        findings = []
        for cluster in get_clusters(self.nbapi, self._cluster):
            if self._wanted(LIMIT_DEVICES):
                findings.extend(
                    DiscoveredFinding('device', device, cluster)
                    for device in self.nbapi.dcim.devices.filter(
                        cluster_id=cluster.id))

            if self._wanted(LIMIT_VMS):
                findings.extend(
                    DiscoveredFinding('virtual-machine', vm, cluster)
                    for vm in
                    self.nbapi.virtualization.virtual_machines.filter(
                        cluster_id=cluster.id))

        return findings
