from ..command import LintCommand
from ..util import split_subinterface
from .findings import InterfaceFinding


def by_device_and_name(ifaces):
    """
    Index interfaces by (device id, name)

    NetBox does not allow one device two interfaces of the same name,
    so this is a key rather than a bucket.
    """
    return {(iface.device.id, iface.name): iface for iface in ifaces}


def wrong_parent(iface, parent_name, by_name):
    """
    Why this subinterface's parent is wrong, or None when it is right

    swp3.1234 belongs to swp3 on the same device, and 'parent' is the
    field that says so. Three ways for it not to:

    - unset, which is the common one -- nothing forces it, and an
      interface created by hand or by an import often has no parent at
      all;
    - set to something else, which is what a rename or a copied record
      leaves behind;
    - naming a parent that does not exist on the device, which is a
      subinterface of nothing.

    The comparison is by id. Names are unique per device, so the id
    and the name say the same thing here -- except when the parent
    sits on *another* device, which the id catches and the name does
    not.
    """
    wanted = by_name.get((iface.device.id, parent_name))
    parent = getattr(iface, 'parent', None)

    if wanted is None:
        if parent is None:
            return f"no interface named '{parent_name}' on this device"

        return (
            f"parent '{parent.name}' #{parent.id} but no interface "
            f"named '{parent_name}' on this device")

    if parent is None:
        return f"no parent set, should be '{wanted.name}' #{wanted.id}"

    if parent.id != wanted.id:
        return (
            f"parent '{parent.name}' #{parent.id}, should be "
            f"'{wanted.name}' #{wanted.id}")

    return None


def find_wrong_parents(ifaces):
    "The numeric subinterfaces whose parent is not the obvious one"
    ifaces = list(ifaces)
    by_name = by_device_and_name(ifaces)

    found = []
    for iface in ifaces:
        split = split_subinterface(iface.name)
        if split is None:
            continue

        parent_name, _number = split
        note = wrong_parent(iface, parent_name, by_name)
        if note is not None:
            found.append((iface, note))

    return found


class SubinterfaceParentsCommand(LintCommand):
    name = 'subinterface-parents'
    help = (
        'Find numeric subinterfaces whose parent is not the interface '
        'their name names. swp3.1234 belongs to swp3 on the same device; '
        'this reports the ones with no parent set, the ones pointing '
        'somewhere else, and the ones whose name implies a parent that '
        'does not exist. Nothing in NetBox enforces this, and the '
        'interface commands here go by the name because of it.')

    def find(self):
        return [
            InterfaceFinding(iface, note=note)
            for iface, note in find_wrong_parents(
                self.nbapi.dcim.interfaces.all())]
