from .exceptions import NotFound
from .util import natsort_key


class NetboxVm:
    @classmethod
    def get_by_name(cls, nbapi, name):
        vm = nbapi.virtualization.virtual_machines.get(name=name)
        if not vm:
            raise NotFound(name)

        return cls(nbapi, vm)

    def __init__(self, nbapi, vm):
        self.nb = nbapi
        self.name = vm.name
        self.vm = vm

    def get_interfaces(self):
        "Get all interfaces on the VM"
        interfaces = list(self.nb.virtualization.interfaces.filter(
            virtual_machine_id=self.vm.id))
        # For now, assume untagged stuff.
        for interface in interfaces:
            assert interface.mode is None, interface.serialize()
            assert interface.enabled, interface.serialize()
        interfaces.sort(key=(lambda x: natsort_key(x.name)))
        return interfaces

    def get_ip_addresses_by_interface(self, iface):
        "Find the gateways of the IPs on the interface"
        # Assert that the interface belongs to this device.
        assert iface.virtual_machine.id == self.vm.id, (
            self.vm, self.vm.id, iface, iface.virtual_machine.id)

        ipaddrs = list(self.nb.ipam.ip_addresses.filter(
            # assigned_object_type='virtualization.vminterface',
            assigned_object_id=iface.id))
        # This is a bit convoluted. We could also do: assigned_object_type=???
        # in the search, but we don't know if/why it is '???'.
        ipaddrs = [
            i for i in ipaddrs
            if i.assigned_object_type == 'virtualization.vminterface']

        return ipaddrs

#
#{'id': 2132, 'url': 'https://netbox.osso.nl
#        turn list(interfaces)
#        breakpoint()
#        print(interfaces)
#
#        if not parent_iface:
#            raise NotFound(name)
#
#        interfaces = [parent_iface]
#
#        if with_subinterfaces:
#            # Technically. we should just need this loop.
#            by_id = set(self.nb.dcim.interfaces.filter(
#                device_id=self.device.id,
#                parent_id=parent_iface.id))
#
#            # But, because we're not 100% confident that everything is
#            # properly set, we'll check by name too.
#            by_name = set(self.nb.dcim.interfaces.filter(
#                device_id=self.device.id,
#                name__isw=f'{name}.'))
#
#            # Check that ifaces by name and by id are the same.
#            by_id_tst = {(iface.name, iface.id) for iface in by_id}
#            by_name_tst = {(iface.name, iface.id) for iface in by_name}
#            by_id_excess = (by_id_tst - by_name_tst)
#            by_name_excess = (by_name_tst - by_id_tst)
#            assert not by_id_excess, by_id_excess
#            assert not by_name_excess, by_name_excess
#
#            interfaces.extend(sorted(by_id, key=(
#                lambda x: natsort_key(x.name))))
#
#        return interfaces

