from argparse import ArgumentParser

import pytest

from nbtools.lintcmd.iface_cables import UnattachedInterfacesCommand

from ..nbstub import FakeNetbox


def reported(nb, require_ip=True, excludes=()):
    "The findings as DEV:IFACE, the way --porcelain prints them"
    cmd = UnattachedInterfacesCommand(nb)
    cmd.set_require_ip(require_ip)
    cmd.set_excludes(excludes)

    return [finding.porcelain() for finding in cmd.find()]


def a_netbox():
    """
    leaf1 with one port of each kind this is about, and leaf2 on the
    far end of the one cable.
    """
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    leaf2 = nb.add_device('leaf2')

    # Cabled, with an address: fine.
    swp1 = nb.add_interface(leaf1, 'swp1')
    nb.add_cable(swp1, nb.add_interface(leaf2, 'swp1'))
    nb.add_ip('10.0.0.1/31', iface=swp1)

    # Uncabled with an address: reported.
    nb.add_ip('10.0.0.3/31', iface=nb.add_interface(leaf1, 'swp2'))

    # Uncabled without one: reported only with --no-require-ip.
    nb.add_interface(leaf1, 'swp3')

    return nb


def test_an_uncabled_interface_with_an_address_is_reported():
    assert reported(a_netbox()) == ['leaf1:swp2']


def test_the_note_gives_the_address():
    [finding] = UnattachedInterfacesCommand(a_netbox()).find()

    assert str(finding) == 'leaf1:swp2 #502 ip=10.0.0.3/31'


def test_no_require_ip_reports_the_interfaces_without_one_too():
    assert reported(a_netbox(), require_ip=False) == [
        'leaf1:swp2', 'leaf1:swp3']


def test_the_far_end_of_a_cable_is_cabled_as_well():
    "leaf2:swp1 holds no address, so this is the cable and not the IP"
    assert 'leaf2:swp1' not in reported(a_netbox(), require_ip=False)


def test_without_the_ip_requirement_there_is_no_note():
    cmd = UnattachedInterfacesCommand(a_netbox())
    cmd.set_require_ip(False)

    assert [str(finding) for finding in cmd.find()] == [
        'leaf1:swp2 #502', 'leaf1:swp3 #503']


def test_an_address_on_a_subinterface_counts_for_its_parent():
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    swp1 = nb.add_interface(leaf1, 'swp1')
    sub = nb.add_interface(leaf1, 'swp1.1234', parent=swp1)
    nb.add_ip('10.1.2.7/24', iface=sub)
    nb.add_ip('10.1.3.7/24', iface=sub)

    assert [str(finding) for finding in
            UnattachedInterfacesCommand(nb).find()] == [
        'leaf1:swp1 #500 ip=10.1.2.7/24 (+1 more)']


def test_an_address_on_a_same_named_port_elsewhere_does_not_count():
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    leaf2 = nb.add_device('leaf2')
    nb.add_interface(leaf1, 'swp1')
    nb.add_ip('10.0.0.1/31', iface=nb.add_interface(leaf2, 'swp1'))

    assert reported(nb) == ['leaf2:swp1']


def test_an_address_on_the_lag_counts_for_its_members():
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    bond0 = nb.add_interface(leaf1, 'bond0', type_='lag')
    bond1 = nb.add_interface(leaf1, 'bond1', type_='lag')
    nb.add_interface(leaf1, 'swp1', lag=bond0)
    nb.add_interface(leaf1, 'swp2', lag=bond1)
    nb.add_interface(leaf1, 'swp3', lag=bond1)
    nb.add_ip('10.0.0.1/31', iface=bond0)
    nb.add_ip('10.1.2.7/24', iface=nb.add_interface(
        leaf1, 'bond1.1234', parent=bond1))

    assert [str(finding) for finding in
            UnattachedInterfacesCommand(nb).find()] == [
        'leaf1:swp1 #502 ip=10.0.0.1/31',
        'leaf1:swp2 #503 ip=10.1.2.7/24',
        'leaf1:swp3 #504 ip=10.1.2.7/24']


def test_a_disabled_interface_is_left_alone():
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    nb.add_ip('10.0.0.1/31', iface=nb.add_interface(
        leaf1, 'swp1', enabled=False))

    assert reported(nb) == []


def test_an_interface_marked_connected_is_left_alone():
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    nb.add_ip('10.0.0.1/31', iface=nb.add_interface(
        leaf1, 'swp1', mark_connected=True))

    assert reported(nb) == []


@pytest.mark.parametrize('type_', [
    'virtual', 'bridge', 'lag', 'ieee802.11ax', 'ieee802.15.1',
    'other-wireless'])
def test_an_interface_that_cannot_take_a_cable_is_left_alone(type_):
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    nb.add_ip('10.0.0.1/31', iface=nb.add_interface(
        leaf1, 'if0', type_=type_))

    assert reported(nb) == []


def test_a_subinterface_is_left_alone_by_name_or_by_parent():
    "Typed as a port, so it is the subinterface rule that skips them"
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    swp1 = nb.add_interface(leaf1, 'swp1')
    nb.add_cable(swp1)
    nb.add_interface(leaf1, 'swp1.1234', type_='1000base-t')
    nb.add_interface(leaf1, 'odd-child', parent=swp1, type_='1000base-t')

    assert reported(nb, require_ip=False) == []


def test_the_loopback_is_left_alone_whatever_its_type():
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    nb.add_ip('10.255.0.1/32', iface=nb.add_interface(
        leaf1, 'lo', type_='1000base-t'))

    assert reported(nb) == []


def test_a_vm_interface_address_does_not_count():
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    nb.add_interface(leaf1, 'eth0')
    nb.add_ip('10.0.0.1/31', iface=nb.add_vm_interface(
        nb.add_vm('vm1'), 'eth0'))

    assert reported(nb) == []


def test_the_exclusions_hold_when_netbox_ignores_the_filters():
    "An unknown filter is dropped, and the whole table comes back"
    nb = a_netbox()
    leaf1 = nb.dcim.devices.get(name='leaf1')
    nb.add_ip('10.0.0.5/31', iface=nb.add_interface(
        leaf1, 'swp4', enabled=False))
    nb.add_ip('10.0.0.7/31', iface=nb.add_interface(
        leaf1, 'vlan100', type_='virtual'))
    nb.dcim.interfaces.filter = (lambda **kwargs: nb.dcim.interfaces.all())

    assert reported(nb) == ['leaf1:swp2']


def test_only_the_ports_holding_an_address_are_listed():
    "The uncabled ports holding nothing are the ones not worth reading"
    nb = a_netbox()
    asked = []
    filter_ = nb.dcim.interfaces.filter
    nb.dcim.interfaces.filter = (
        lambda **kwargs: asked.append(kwargs) or filter_(**kwargs))

    assert reported(nb) == ['leaf1:swp2']
    assert asked and all(
        'name' in kwargs or 'lag_id' in kwargs for kwargs in asked)


def test_the_cross_product_of_devices_and_names_is_not_reported():
    "Asked for leaf1:swp1 and leaf2:swp2, NetBox also answers the swap"
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    leaf2 = nb.add_device('leaf2')
    nb.add_ip('10.0.0.1/31', iface=nb.add_interface(leaf1, 'swp1'))
    nb.add_ip('10.0.0.3/31', iface=nb.add_interface(leaf2, 'swp2'))
    nb.add_interface(leaf1, 'swp2')
    nb.add_interface(leaf2, 'swp1')

    assert reported(nb) == ['leaf1:swp1', 'leaf2:swp2']


def test_a_lag_member_holding_an_address_itself_is_reported_once():
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    bond0 = nb.add_interface(leaf1, 'bond0', type_='lag')
    nb.add_ip('10.0.0.1/31', iface=bond0)
    nb.add_ip('10.0.0.3/31', iface=nb.add_interface(
        leaf1, 'swp1', lag=bond0))

    assert reported(nb) == ['leaf1:swp1']


def test_findings_are_ordered_by_device_then_interface():
    nb = FakeNetbox()
    leaf2 = nb.add_device('leaf2')
    leaf1 = nb.add_device('leaf1')
    for device, name in (
            (leaf2, 'swp1'), (leaf1, 'swp2'), (leaf1, 'swp1')):
        nb.add_ip('10.0.0.1/31', iface=nb.add_interface(device, name))

    assert reported(nb) == ['leaf1:swp1', 'leaf1:swp2', 'leaf2:swp1']


@pytest.mark.parametrize('argv, require_ip', [
    ([], True),
    (['--require-ip'], True),
    (['--no-require-ip'], False),
    (['--no-require-ip', '--require-ip'], True),
])
def test_the_ip_requirement_is_on_by_default_and_can_be_turned_off(
        argv, require_ip):
    parser = ArgumentParser()
    UnattachedInterfacesCommand.add_arguments(parser)
    cmd = UnattachedInterfacesCommand.from_args(
        a_netbox(), parser.parse_args(argv))

    assert cmd._require_ip is require_ip


def a_netbox_with_odd_ports():
    "a_netbox, and leaf1 with the ports one would rather not hear about"
    nb = a_netbox()
    leaf1 = nb.dcim.devices.get(name='leaf1')
    for name in ('BMC', 'bmc', 'enx0a1b2c3d4e5f', 'enp1s0'):
        nb.add_interface(leaf1, name)

    return nb


@pytest.mark.parametrize('excludes, left_out', [
    ([], set()),
    (['BMC'], {'leaf1:BMC'}),
    (['bmc'], {'leaf1:bmc'}),
    (['enx*'], {'leaf1:enx0a1b2c3d4e5f'}),
    (['BMC', 'enx*'], {'leaf1:BMC', 'leaf1:enx0a1b2c3d4e5f'}),
    (['swp[23]'], {'leaf1:swp2', 'leaf1:swp3'}),
    (['leaf1:swp2'], set()),
])
def test_exclude_leaves_out_the_names_it_matches(excludes, left_out):
    nb = a_netbox_with_odd_ports()
    everything = reported(nb, require_ip=False)

    assert left_out <= set(everything)
    assert reported(nb, require_ip=False, excludes=excludes) == [
        name for name in everything if name not in left_out]


def test_exclude_holds_with_the_ip_requirement_too():
    assert reported(a_netbox(), excludes=['swp*']) == []


@pytest.mark.parametrize('argv, excludes', [
    ([], ()),
    (['--exclude=BMC'], ('BMC',)),
    (['--exclude', 'BMC', '--exclude=enx*'], ('BMC', 'enx*')),
    (['--exclude=BMC, enx*', '--exclude=eno1'], ('BMC', 'enx*', 'eno1')),
])
def test_exclude_is_repeatable_or_comma_separated(argv, excludes):
    parser = ArgumentParser()
    UnattachedInterfacesCommand.add_arguments(parser)
    cmd = UnattachedInterfacesCommand.from_args(
        a_netbox(), parser.parse_args(argv))

    assert cmd._excludes == excludes


@pytest.mark.parametrize('value', ['', 'BMC,', ',BMC', 'BMC,,enx*'])
def test_an_empty_exclude_is_refused(value, capsys):
    parser = ArgumentParser()
    UnattachedInterfacesCommand.add_arguments(parser)

    with pytest.raises(SystemExit):
        parser.parse_args([f'--exclude={value}'])
    assert 'empty interface name' in capsys.readouterr().err


def test_command_reports_and_counts(capsys):
    assert UnattachedInterfacesCommand(a_netbox()).run() == 1
    assert capsys.readouterr().out == (
        '---------------------\n'
        'unattached-interfaces\n'
        '---------------------\n'
        '- leaf1:swp2 #502 ip=10.0.0.3/31\n')


def test_porcelain_prints_what_the_nbsync_interface_commands_take(capsys):
    cmd = UnattachedInterfacesCommand(a_netbox())
    cmd.set_porcelain()

    assert cmd.run() == 1
    assert capsys.readouterr().out == 'leaf1:swp2\n'


def test_a_clean_netbox_is_silent(capsys):
    assert UnattachedInterfacesCommand(FakeNetbox()).run() == 0
    assert capsys.readouterr().out == ''
