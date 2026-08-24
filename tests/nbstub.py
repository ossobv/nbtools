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


# Where each kind of record starts counting. Deliberately far apart:
# device #5 and virtual machine #5 are not the same machine, and a test
# that mixes the two up should say so rather than pass.
FIRST_ID = {
    'vrfs': 300,
    'devices': 400,
    'interfaces': 500,
    'virtual_machines': 700,
    'vminterfaces': 800,
    'ip_addresses': 900,
}


class Named(NS):
    """
    A record that renders as its name, the way a pynetbox one does

    It hashes by id too, because get_interfaces_by_name() puts
    interfaces in a set and a plain SimpleNamespace is unhashable.
    """
    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(self.id)


def _rel_id(record, name):
    "The id of a related record, or None when it has none"
    related = getattr(record, name, None)
    return (related.id if related is not None else None)


def _assigned_id(record, kind):
    "The id of the assigned object, but only if it is of this kind"
    if record.assigned_object_type != kind:
        return None
    return record.assigned_object.id


# How a filter keyword picks its records. NetBox has one of these per
# relation; only the ones the commands actually pass are listed, so an
# unknown keyword raises instead of quietly matching everything.
FILTERS = {
    'id': (lambda rec, val: rec.id == val),
    'name': (lambda rec, val: rec.name == val),
    'name__isw': (lambda rec, val: rec.name.lower().startswith(val.lower())),
    'address': (lambda rec, val: str(rec.address) == str(val)),
    'device_id': (lambda rec, val: _rel_id(rec, 'device') == val),
    'parent_id': (lambda rec, val: _rel_id(rec, 'parent') == val),
    'virtual_machine_id': (
        lambda rec, val: _rel_id(rec, 'virtual_machine') == val),
    'interface_id': (
        lambda rec, val: _assigned_id(rec, 'dcim.interface') == val),
    'vminterface_id': (
        lambda rec, val: _assigned_id(
            rec, 'virtualization.vminterface') == val),
}


class FakeEndpoint:
    """
    The calls a command makes on one NetBox endpoint, over a list

    The writes land in the same list the reads come from, which is the
    point of it: a CreateInterface, and then the named_lambda that
    looks the new interface up by name, have to agree.
    """
    def __init__(self, records=(), on_create=None, on_update=None):
        self.records = list(records)
        self.created = []
        self.updated = []
        self.deleted = []
        self._on_create = on_create
        self._on_update = on_update

    def all(self):
        return list(self.records)

    def filter(self, *args, **kwargs):
        assert not args, f'freeform search not stubbed here: {args}'
        return [
            record for record in self.records
            if all(FILTERS[key](record, value)
                   for key, value in kwargs.items())]

    def get(self, *args, **kwargs):
        if args:
            # nbapi.dcim.interfaces.get(5319), the by-id form.
            assert len(args) == 1 and not kwargs, (args, kwargs)
            kwargs = {'id': args[0]}

        found = self.filter(**kwargs)
        assert len(found) <= 1, found
        return (found[0] if found else None)

    def create(self, values):
        assert self._on_create, 'this endpoint does not create'
        record = self._on_create(values)
        self.records.append(record)
        self.created.append(values)
        return record

    def update(self, updates):
        assert self._on_update, 'this endpoint does not update'
        for update in updates:
            values = dict(update)
            record = self.get(values.pop('id'))
            assert record is not None, update
            self._on_update(record, values)
            self.updated.append(update)

    def delete(self, ids):
        for id_ in ids:
            record = self.get(id_)
            assert record is not None, id_
            self.records.remove(record)
            self.deleted.append(id_)


class FakeNetbox:
    """
    A small NetBox held in memory: VRFs, devices, interfaces, VMs, IPs

    Enough for migrate-gateway, which reads five endpoints and writes to
    two. A recording would show the same calls, but it takes a real
    NetBox to make one and forty entries of JSON to read it; what the
    tests are about here is which subinterface an IP ends up on, and
    that is one assert against this.

    Build it by adding records, then hand the instance to the command:

        nb = FakeNetbox()
        red = nb.add_vrf('vrf-red')
        leaf1 = nb.add_device('leaf1')
        swp34 = nb.add_interface(leaf1, 'swp34')
        sub = nb.add_interface(leaf1, 'swp34.1234', parent=swp34, vrf=red)
    """
    def __init__(self):
        self._next_id = dict(FIRST_ID)

        self.ipam = NS(
            vrfs=FakeEndpoint(),
            ip_addresses=FakeEndpoint(on_update=self._update_ip))
        self.dcim = NS(
            devices=FakeEndpoint(),
            interfaces=FakeEndpoint(on_create=self._create_interface))
        self.virtualization = NS(
            virtual_machines=FakeEndpoint(),
            interfaces=FakeEndpoint())

    def _take_id(self, kind):
        id_ = self._next_id[kind]
        self._next_id[kind] = id_ + 1
        return id_

    # -- reading side: build the world --

    def add_vrf(self, name):
        vrf = Named(id=self._take_id('vrfs'), name=name)
        self.ipam.vrfs.records.append(vrf)
        return vrf

    def add_device(self, name):
        device = Named(id=self._take_id('devices'), name=name)
        self.dcim.devices.records.append(device)
        return device

    def add_interface(self, device, name, parent=None, vrf=None, type_=None):
        "A dcim.interface, with the fields the interface commands copy"
        iface = self.make_interface(
            device, name, parent=parent, vrf=vrf, type_=type_)
        self.dcim.interfaces.records.append(iface)
        return iface

    def make_interface(self, device, name, parent=None, vrf=None, type_=None):
        "Build the record without filing it; create() does the filing"
        if type_ is None:
            type_ = ('virtual' if parent else '1000base-t')

        iface = Named(
            id=self._take_id('interfaces'), name=name, device=device,
            parent=parent, vrf=vrf, description='', enabled=True, label='',
            mode=None, tags=[], tagged_vlans=[], untagged_vlan=None,
            type=NS(value=type_, label=type_), cable=None)
        return iface

    def add_vm(self, name):
        vm = Named(
            id=self._take_id('virtual_machines'), name=name)
        self.virtualization.virtual_machines.records.append(vm)
        return vm

    def add_vm_interface(self, vm, name):
        iface = Named(
            id=self._take_id('vminterfaces'), name=name, virtual_machine=vm,
            enabled=True, mode=None)
        self.virtualization.interfaces.records.append(iface)
        return iface

    def add_ip(self, address, iface=None, vrf=None):
        "An ipam.ip_address, on a device interface, a VM interface or neither"
        ipaddr = Named(
            id=self._take_id('ip_addresses'), address=address, vrf=vrf,
            name=address,
            description='', dns_name='', role=None, tags=[], tenant=None,
            status=NS(value='active', label='Active'),
            assigned_object=iface,
            assigned_object_type=self._object_type(iface))
        self.ipam.ip_addresses.records.append(ipaddr)
        return ipaddr

    @staticmethod
    def _object_type(iface):
        if iface is None:
            return None
        if getattr(iface, 'virtual_machine', None) is not None:
            return 'virtualization.vminterface'
        return 'dcim.interface'

    # -- writing side: what the work items do --

    def _create_interface(self, values):
        "Turn the POST body back into a record, ids resolved to objects"
        return self.make_interface(
            self.dcim.devices.get(values['device']),
            values['name'],
            parent=(
                self.dcim.interfaces.get(values['parent'])
                if values.get('parent') else None),
            vrf=(
                self.ipam.vrfs.get(values['vrf'])
                if values.get('vrf') else None),
            type_=values.get('type'))

    def _update_ip(self, record, values):
        for key, value in values.items():
            setattr(record, key, value)

        if 'assigned_object_id' in values:
            assert record.assigned_object_type == 'dcim.interface', record
            record.assigned_object = self.dcim.interfaces.get(
                values['assigned_object_id'])

    # -- what the tests ask about afterwards --

    def where_is(self, ipaddr):
        "'leaf1:swp34.1234' for an assigned IP, or None"
        iface = self.ipam.ip_addresses.get(ipaddr.id).assigned_object
        if iface is None:
            return None

        holder = getattr(iface, 'device', None) or iface.virtual_machine
        return f'{holder.name}:{iface.name}'
