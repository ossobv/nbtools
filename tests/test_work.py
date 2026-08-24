from nbtools.work import (
    ModifyCable, ModifyIPAddress, ReassignIPAddress, named_id)


# A real NetBox device name, shortened.
SPACED_DEV = 'FREE (was-planned: node3.example.com)'


def test_ip_work_quotes_device_with_space():
    dev = named_id(SPACED_DEV, 1, parent=None)
    iface = named_id('BMC', 2, parent=dev)
    ip = named_id('10.20.30.40/24', 3, parent=iface)

    assert str(ModifyIPAddress(ip, {'status': 'dhcp'})) == (
        f"'{SPACED_DEV}':BMC set ip 10.20.30.40/24 status=dhcp")


def test_ip_work_leaves_plain_device_unquoted():
    dev = named_id('node3.example.com', 1, parent=None)
    iface = named_id('BMC', 2, parent=dev)
    ip = named_id('10.20.30.40/24', 3, parent=iface)

    assert str(ModifyIPAddress(ip, {'status': 'dhcp'})) == (
        'node3.example.com:BMC set ip 10.20.30.40/24 status=dhcp')


def test_cable_work_quotes_device_with_space():
    "ModifyCable used to read .name directly, skipping the quoting"
    dev = named_id(SPACED_DEV, 1, parent=None)
    iface = named_id('swp52', 2, parent=dev)
    cable = named_id('#293', 293, parent=iface)

    assert str(ModifyCable(cable, {'b_terminations': []})) == (
        f"'{SPACED_DEV}':swp52 cable #293 set b_terminations=[]")


def test_a_reassign_without_a_vrf_says_only_where_the_ip_lands():
    "migrate-gateway moves an IP without touching the VRF it is routed in"
    dev = named_id('leaf3', 4, parent=None)
    iface = named_id('swp8.1234', 5, parent=dev)
    ip = named_id('10.0.0.0/31', 3, parent=iface)

    assert str(ReassignIPAddress(ip, {
        'assigned_object_type': 'dcim.interface',
        'assigned_object_id': 5,
    })) == 'leaf3:swp8.1234 add ip 10.0.0.0/31'


def test_a_reassign_that_writes_a_vrf_names_it():
    "set-interface-ip sets the VRF as it takes the IP over"
    dev = named_id('leaf3', 4, parent=None)
    iface = named_id('swp8.1234', 5, parent=dev)
    ip = named_id('10.0.0.0/31', 3, parent=iface)
    vrf = named_id('vrf-red', 9, parent=None)

    assert str(ReassignIPAddress(ip, {
        'assigned_object_type': 'dcim.interface',
        'assigned_object_id': 5,
        'vrf': vrf,
    })) == 'leaf3:swp8.1234 add ip 10.0.0.0/31 vrf vrf-red'
