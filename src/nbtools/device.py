from .exceptions import NotFound
from .util import natsort_key


class NetboxDevice:
    @classmethod
    def get_by_name(cls, nbapi, name):
        device = nbapi.dcim.devices.get(name=name)
        if not device:
            raise NotFound(name)

        return cls(nbapi, device)

    def __init__(self, nbapi, device):
        self.nb = nbapi
        self.name = device.name
        self.device = device

    def get_interfaces_by_name(self, name, with_subinterfaces=True):
        "Get swp34 or swp34 and swp34.12, swp34.13, swp34.14 with vlan"
        parent_iface = self.nb.dcim.interfaces.get(
            device_id=self.device.id, name=name)
        if not parent_iface:
            raise NotFound(name)

        interfaces = [parent_iface]

        if with_subinterfaces:
            # Technically. we should just need this loop.
            by_id = set(self.nb.dcim.interfaces.filter(
                device_id=self.device.id,
                parent_id=parent_iface.id))

            # But, because we're not 100% confident that everything is
            # properly set, we'll check by name too.
            by_name = set(self.nb.dcim.interfaces.filter(
                device_id=self.device.id,
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

    def get_ip_addresses_by_interface(self, iface):
        "Find source IPs, but make sure that we're dealing with physical hosts"
        # Assert that the interface belongs to this device.
        assert iface.device.id == self.device.id, (
            self.device, self.device.id, iface, iface.device.id)

        # Useful? Or old crap?
        # #assert (
        # #    iface.parent is not None
        # #    or iface.link_peers_type == 'dcim.interface'), (
        # #        iface, iface.link_peers_type)

        assert iface.__class__.__module__ == 'pynetbox.models.dcim', (
            iface, iface.__class__)
        ipaddrs = list(self.nb.ipam.ip_addresses.filter(
            # assigned_object_type='dcim.interface',
            assigned_object_id=iface.id))
        # This is a bit convoluted. We could also do: assigned_object_type=5
        # in the search, but we don't know why it is '5'.
        ipaddrs = [
            i for i in ipaddrs if i.assigned_object_type == 'dcim.interface']

        return ipaddrs
