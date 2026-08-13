from nbtools.work import ModifyCable, ModifyIPAddress, named_id


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
