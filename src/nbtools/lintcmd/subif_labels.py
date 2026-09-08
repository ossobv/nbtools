from ..command import LintCommand
from ..util import split_subinterface

from .findings import InterfaceFinding


def vrf_of(iface):
    "The name of the VRF an interface is in, or None"
    vrf = getattr(iface, 'vrf', None)

    return (str(vrf.name) if vrf is not None else None)


def label_of(iface):
    "The label an interface carries, '' when it carries none"
    return str(getattr(iface, 'label', '') or '')


def wrong_label(iface):
    """
    Why this subinterface's label is wrong, or None when it is right

    The rule is that the label spells out the VRF: swp1.1234 in VRF
    STAIRS is labelled STAIRS. This is purely convention and easy
    on the eyes in NetBox.

    A subinterface with no VRF at all is not this check's business,
    except when it carries a label anyway, which might be a label
    left behind by a VRF that moved.
    """
    vrf = vrf_of(iface)
    label = label_of(iface)

    if vrf is None:
        if label:
            return f"label '{label}' but no vrf"
        return None

    if label != vrf:
        return f"label '{label}' should be '{vrf}'"

    return None


def find_mislabelled_subinterfaces(ifaces):
    "The numeric subinterfaces whose label does not spell out their VRF"
    found = []
    for iface in ifaces:
        if split_subinterface(iface.name) is None:
            continue

        note = wrong_label(iface)
        if note is not None:
            found.append((iface, note))

    return found


class SubinterfaceLabelsCommand(LintCommand):
    name = 'subinterface-labels'
    help = (
        'Find numeric subinterfaces whose label does not spell out their '
        'VRF. swp1.1234 in VRF STAIRS should be labelled STAIRS: '
        'the number on its own does not tell a reader which '
        'VRF 1234 is. Non-numeric suffixes are left alone.')

    def find(self):
        return [
            InterfaceFinding(iface, note=note)
            for iface, note in find_mislabelled_subinterfaces(
                self.nbapi.dcim.interfaces.all())]
