from nbtools.work import (
    ModifyCable, ModifyIPAddress, named_id, quoted_name)


# A real NetBox device name, shortened.
SPACED_DEV = 'FREE (was-planned: node3.example.com)'


def test_quoted_name_leaves_plain_name_alone():
    assert quoted_name('node3.example.com') == 'node3.example.com'


def test_quoted_name_quotes_name_with_space():
    assert quoted_name(SPACED_DEV) == f"'{SPACED_DEV}'"


def test_quoted_name_doubles_embedded_quote():
    assert quoted_name("Bob's spare (old)") == "'Bob''s spare (old)'"


def test_quoted_name_quotes_on_a_quote_alone():
    "Else a leading quote reads as the start of a quoted name"
    assert quoted_name("'weird") == "'''weird'"


def test_quoted_name_leaves_backslash_alone():
    "Only the quote is special; a backslash needs no second rule"
    assert quoted_name('c:\\some path') == "'c:\\some path'"


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
