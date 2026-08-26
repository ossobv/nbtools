from ..command import LintCommand
from ..util import split_subinterface
from .findings import InterfaceFinding
from .subif_labels import vrf_of


# How many VRF-carrying subinterfaces make the parent's own VRF wrong.
# Two: one subinterface in a VRF and a parent in the same VRF is a
# plain layout, but as soon as the port carries a second VRF the
# parent cannot be in one of them without lying about the other.
MULTIPLE = 2


def find_parents_in_a_vrf(ifaces, multiple=MULTIPLE):
    """
    Parent interfaces that are in a VRF while their children are too

    Returns [(parent, child_vrfs)] with child_vrfs sorted, for the
    interfaces that have several subinterfaces carrying VRFs and a VRF
    of their own on top.

    Grouping is by name rather than by parent_id. netbox.py already
    distrusts parent_id enough to cross-check it against the name, and
    an interface whose parent_id is simply not set is exactly the kind
    of record a linter is run to find -- so going by the name reports
    it instead of skipping it.
    """
    by_parent = {}
    for iface in ifaces:
        split = split_subinterface(iface.name)
        if split is None:
            continue

        vrf = vrf_of(iface)
        if vrf is None:
            continue

        parent_name, _number = split
        by_parent.setdefault((iface.device.id, parent_name), []).append(vrf)

    found = []
    for iface in ifaces:
        child_vrfs = by_parent.get((iface.device.id, iface.name), [])
        if len(child_vrfs) < multiple:
            continue

        if vrf_of(iface) is None:
            continue

        found.append((iface, sorted(child_vrfs)))

    return found


class ParentInterfaceVrfsCommand(LintCommand):
    name = 'parent-interface-vrfs'
    help = (
        'Find interfaces that are in a VRF while carrying several '
        'subinterfaces that are each in one. The port itself belongs to '
        'no single VRF then, so its own should be cleared.')

    def find(self):
        return [
            InterfaceFinding(iface, note=(
                f"vrf '{vrf_of(iface)}' but subinterfaces in "
                f'{len(child_vrfs)} vrfs '
                f'({", ".join(child_vrfs)})'))
            for iface, child_vrfs in find_parents_in_a_vrf(
                self.nbapi.dcim.interfaces.all())]
