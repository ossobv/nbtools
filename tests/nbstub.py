"""
Hand-rolled stand-ins for the pynetbox objects.

The recorded fixtures next to the tests in synccmd/ suit the commands
that talk to a lot of NetBox at once: they pin the request bodies, and
they were cheap to make because a real run produced them. These stubs
suit the other kind, where the logic is small and a recording would
bury it.
"""
from types import SimpleNamespace as NS


def an_iface(name, devname, id_=5319, devid=538):
    return NS(id=id_, name=name, device=NS(id=devid, name=devname))


def a_vm_iface(name, vmname, id_=100, vmid=7):
    """
    Stand in for a virtualization.vminterface

    It has .virtual_machine and no .device at all, and its id comes
    from a different table than a dcim.interface id.
    """
    return NS(id=id_, name=name, virtual_machine=NS(id=vmid, name=vmname))


def a_mac(id_, value, iface=None):
    "Stand in for a pynetbox dcim.mac_addresses record"
    if iface is None:
        kind = None
    elif getattr(iface, 'virtual_machine', None) is not None:
        kind = 'virtualization.vminterface'
    else:
        kind = 'dcim.interface'

    return NS(
        id=id_, mac_address=value, assigned_object=iface,
        assigned_object_type=kind)


def an_nbapi(*macs, iface=None):
    """
    An nbapi holding these MAC records.

    Pass iface to make the device and interface lookups resolve to it,
    for the commands that take a DEV:IFACE target.
    """
    def filter_macs(q=None, **kwargs):
        # Stand in for the freeform q= search, substring matches and all.
        return [
            mac for mac in macs
            if q is None or q.lower() in str(mac.mac_address).lower()]

    nbapi = NS(dcim=NS(
        mac_addresses=NS(all=(lambda: list(macs)), filter=filter_macs),
        devices=NS(get=(lambda **kwargs: iface and iface.device)),
        interfaces=NS(
            get=(lambda **kwargs: iface),
            filter=(lambda **kwargs: []))))

    # What was deleted, for the tests that execute a plan.
    nbapi.deleted = []
    nbapi.dcim.mac_addresses.delete = nbapi.deleted.append

    return nbapi
