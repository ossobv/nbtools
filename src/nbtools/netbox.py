from collections import namedtuple

from .exceptions import NotFound
from .types import DevIface
from .util import natsort_key


# The interface we were asked about, plus its subinterfaces. Shared by
# every command that operates on an interface and its children.
InterfaceTree = namedtuple(
    'InterfaceTree', 'dev if_name if_parent if_children')


def get_device(nbapi, name):
    "Get the device by name"
    device = nbapi.dcim.devices.get(name=name)
    if not device:
        raise NotFound(name)

    return device


def get_interfaces_by_name(nbapi, device, name, with_subinterfaces=True):
    "Get swp34 or swp34 and swp34.12, swp34.13, swp34.14 with vlan"
    parent_iface = nbapi.dcim.interfaces.get(device_id=device.id, name=name)
    if not parent_iface:
        raise NotFound(name)

    interfaces = [parent_iface]

    if with_subinterfaces:
        # Technically. we should just need this loop.
        by_id = set(nbapi.dcim.interfaces.filter(
            device_id=device.id,
            parent_id=parent_iface.id))

        # But, because we're not 100% confident that everything is
        # properly set, we'll check by name too.
        by_name = set(nbapi.dcim.interfaces.filter(
            device_id=device.id,
            name__isw=f'{name}.'))

        # Check that ifaces by name and by id are the same.
        by_id_tst = {(iface.name, iface.id) for iface in by_id}
        by_name_tst = {(iface.name, iface.id) for iface in by_name}
        by_id_excess = (by_id_tst - by_name_tst)
        by_name_excess = (by_name_tst - by_id_tst)
        assert not by_id_excess, by_id_excess
        assert not by_name_excess, by_name_excess

        interfaces.extend(sorted(by_id, key=(
            lambda x: natsort_key(x.name))))

    return interfaces


def check_child_interface_names(ifaces, ifacename) -> None:
    "The children of swp34 are expected to be named swp34.something"
    startswith = f'{ifacename}.'
    for iface in ifaces:
        if not iface.name.startswith(startswith):
            raise NotImplementedError(
                f'expected "{iface}" to start with "{startswith}"')


def get_interface_tree(
        nbapi, devif: DevIface, with_subinterfaces=True,
        raise_as=NotFound) -> InterfaceTree:
    """
    Look up a DevIface and its subinterfaces as an InterfaceTree.

    Pass raise_as to label which side of the operation went missing,
    e.g. raise_as=UnrecognisedItemOnSource.
    """
    try:
        device = get_device(nbapi, devif.device)
        ifaces = get_interfaces_by_name(
            nbapi, device, devif.interface,
            with_subinterfaces=with_subinterfaces)
    except NotFound as e:
        raise raise_as(devif) from e

    parent_iface = ifaces.pop(0)
    check_child_interface_names(ifaces, devif.interface)

    return InterfaceTree(
        dev=device,
        if_name=devif.interface,
        if_parent=parent_iface,
        if_children=ifaces,
    )


def get_mac_addresses(nbapi, mac):
    """
    Get every record NetBox holds for this exact MAC address

    Filtering happens twice on purpose. pynetbox turns a q= into a
    freeform search, which also returns neighbours, so the exact match
    is redone here rather than trusted to the server.
    """
    wanted = str(mac).lower()

    return [
        rec for rec in nbapi.dcim.mac_addresses.filter(q=wanted)
        if str(rec.mac_address).lower() == wanted]


def get_ip_addresses(nbapi, iface):
    "Get the IPs assigned to this interface"
    # NOTE: hardware only. For a VM this would be vminterface_id. The
    # old code asserted on iface.__class__.__module__ to catch that,
    # which only ever documented the missing feature.
    return list(nbapi.ipam.ip_addresses.filter(interface_id=iface.id))
