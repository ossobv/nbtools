from ..command import LintCommand
from .findings import InterfaceFinding


# The interface a machine's management controller sits on. Configurable
# because this is a naming convention rather than a NetBox concept, but
# defaulted because it is the convention here.
BMC_NAME = 'BMC'


def macs_by_interface(macs):
    """
    Index MAC records by the dcim.interface they sit on

    assigned_object_type is what says which kind of interface a record
    is on: a dcim.interface id and a virtualization.vminterface id come
    from different tables, so an id alone does not identify one.
    """
    by_iface = {}
    for mac in macs:
        if getattr(mac, 'assigned_object_type', None) != 'dcim.interface':
            continue

        iface = mac.assigned_object
        if iface is None:
            continue

        by_iface.setdefault(iface.id, []).append(mac)

    return by_iface


def find_bad_bmc_macs(ifaces, macs, name=BMC_NAME):
    "The interfaces of that name that do not hold exactly one MAC"
    by_iface = macs_by_interface(macs)
    wanted = name.lower()

    found = []
    for iface in ifaces:
        if str(iface.name).lower() != wanted:
            continue

        on_it = sorted(
            by_iface.get(iface.id, []), key=(lambda mac: mac.id))
        if len(on_it) != 1:
            found.append((iface, on_it))

    return found


def a_note(macs):
    "Say how many MACs there are and, when there are several, which"
    if not macs:
        return 'no mac address'

    detail = ', '.join(
        f'#{mac.id} {str(mac.mac_address).lower()}' for mac in macs)

    return f'{len(macs)} mac addresses: {detail}'


class BmcMacsCommand(LintCommand):
    name = 'bmc-macs'
    help = (
        'Find BMC interfaces that do not hold exactly one MAC address. A '
        'management controller is reached by its MAC before it is reached '
        'by anything else, so none means it cannot be found and two mean '
        'nothing can tell which of them to use.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--name', default=BMC_NAME, metavar='NAME', help=(
            'The interface name that has to hold exactly one MAC '
            f'(default: {BMC_NAME}). Matched without regard to case, so '
            'a "bmc" interface is checked too -- and the whole interface '
            'table is read to do it, rather than trusting a server-side '
            'filter to be case blind.'))

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
        return [
            InterfaceFinding(iface, note=a_note(macs))
            for iface, macs in find_bad_bmc_macs(
                self.nbapi.dcim.interfaces.all(),
                self.nbapi.dcim.mac_addresses.all(),
                name=self._name)]
