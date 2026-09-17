import io
import sys

import pytest

from nbtools.command import ProcessMode, STDIN_ARG
from nbtools.exceptions import UnrecognisedItemOnTarget
from nbtools.synccmd.zap_if import ZapInterfaceCommand
from nbtools.types import DevIface

from ..nbstub import FakeNetbox
from ..nbtest import get_test_api, nb_responses_load


def a_netbox():
    """
    leaf2:swp8 with everything on it a migrate-interface would copy

    Two subinterfaces with an address each, one address on the port
    itself, and a MAC and a cable that are the port's own. leaf2:swp9
    is already bare.
    """
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    leaf1 = nb.add_device('leaf1')
    leaf2 = nb.add_device('leaf2')

    nb.swp8 = nb.add_interface(
        leaf2, 'swp8', vrf=red, label='DEV', tags=['corelink'],
        mode='tagged', tagged_vlans=[nb.add_vlan(100)],
        untagged_vlan=nb.add_vlan(1))
    nb.swp8.description = 'to leaf1'
    nb.sub1 = nb.add_interface(leaf2, 'swp8.1234', parent=nb.swp8, vrf=red)
    nb.sub2 = nb.add_interface(leaf2, 'swp8.1235', parent=nb.swp8, vrf=red)
    nb.add_ip('10.0.0.0/31', iface=nb.sub1, vrf=red)
    nb.add_ip('10.0.0.2/31', iface=nb.sub2, vrf=red)
    nb.add_ip('192.0.2.1/24', iface=nb.swp8)
    nb.mac = nb.add_mac('AA:BB:CC:00:00:08', iface=nb.swp8)
    nb.add_cable(nb.swp8, nb.add_interface(leaf1, 'swp1'))

    nb.swp9 = nb.add_interface(leaf2, 'swp9')
    nb.add_interface(leaf2, 'swp80')

    return nb


def a_command(nb, *targets):
    cmd = ZapInterfaceCommand(nb)
    cmd.set_input_values(list(targets), DevIface)
    return cmd


def test_the_plan_deletes_children_and_ips_and_clears_the_port():
    cmd = a_command(a_netbox(), DevIface('leaf2:swp8'))

    assert [str(future) for future in cmd.plan()] == [
        'leaf2:swp8.1234 del ip 10.0.0.0/31',
        'leaf2 del int swp8.1234',
        'leaf2:swp8.1235 del ip 10.0.0.2/31',
        'leaf2 del int swp8.1235',
        'leaf2:swp8 del ip 192.0.2.1/24',
        'leaf2 set int swp8 description= label= mode=None '
        'tagged_vlans=[] untagged_vlan=None tags=[] vrf=None',
    ]


def test_after_the_zap_only_the_port_and_its_own_things_remain():
    nb = a_netbox()
    assert a_command(nb, DevIface('leaf2:swp8')).run(ProcessMode.YES) == 0

    names = sorted(iface.name for iface in nb.dcim.interfaces.all())
    assert names == ['swp1', 'swp8', 'swp80', 'swp9']
    assert nb.ipam.ip_addresses.all() == []

    swp8 = nb.dcim.interfaces.get(nb.swp8.id)
    assert (swp8.description, swp8.label, swp8.mode, swp8.vrf) == (
        '', '', None, None)
    assert (swp8.tags, swp8.tagged_vlans, swp8.untagged_vlan) == (
        [], [], None)
    assert swp8.type.value == '1000base-t'
    assert swp8.cable is not None
    assert nb.dcim.mac_addresses.all() == [nb.mac]


def test_a_bare_interface_is_no_work():
    cmd = a_command(a_netbox(), DevIface('leaf2:swp9'))

    assert cmd.plan() == []


def test_only_the_fields_that_are_set_get_cleared():
    nb = a_netbox()
    nb.swp9.label = 'DEV'

    cmd = a_command(nb, DevIface('leaf2:swp9'))

    assert [str(future) for future in cmd.plan()] == [
        'leaf2 set int swp9 label=']


def test_an_unknown_interface_is_refused():
    cmd = a_command(a_netbox(), DevIface('leaf2:swp7'))

    with pytest.raises(UnrecognisedItemOnTarget):
        cmd.plan()


def test_the_targets_can_come_off_stdin(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'stdin', io.StringIO(
        'leaf2:swp9\n'
        'leaf2:swp8\n'))
    nb = a_netbox()
    cmd = a_command(nb, STDIN_ARG)

    assert cmd.run(ProcessMode.YES) == 0
    assert 'leaf2 del int swp8.1234' in capsys.readouterr().out
    assert nb.ipam.ip_addresses.all() == []


DEV = 'switch2.dostno.systems'


@nb_responses_load('test_zap_if.0.json', caller=__file__)
def test_zap_iface_0():
    """
    Plan the zap of a recorded port, check the listing, then carry it out

    The recorded fixture answers each call once, in the order it was
    taped, so the plan and its execution happen in one pass. The port
    itself has no address; its description, label and tags get cleared.
    """
    cmd = ZapInterfaceCommand(get_test_api())
    cmd.set_input_values([DevIface(f'{DEV}:swp10')], DevIface)
    cmd.set_quiet()

    work_to_do = cmd.plan()

    assert [str(work) for work in work_to_do] == [
        f'{DEV}:swp10.55 del ip 10.123.5.36/31',
        f'{DEV}:swp10.55 del ip 10.123.5.42/31',
        f'{DEV}:swp10.55 del ip 10.123.5.50/31',
        f'{DEV} del int swp10.55',
        f'{DEV}:swp10.66 del ip 10.123.112.32/31',
        f'{DEV} del int swp10.66',
        f'{DEV}:swp10.94 del ip 10.123.160.34/31',
        f'{DEV} del int swp10.94',
        f'{DEV}:swp10.623 del ip 10.123.144.34/31',
        f'{DEV} del int swp10.623',
        f'{DEV}:swp10.666 del ip 10.123.2.4/31',
        f'{DEV}:swp10.666 del ip 10.123.2.18/31',
        f'{DEV}:swp10.666 del ip 10.123.2.28/31',
        f'{DEV}:swp10.666 del ip 10.123.2.60/31',
        f'{DEV}:swp10.666 del ip 10.123.2.62/31',
        f'{DEV}:swp10.666 del ip 10.123.20.20/31',
        f'{DEV}:swp10.666 del ip 10.123.20.23/31',
        f'{DEV}:swp10.666 del ip 10.123.20.30/31',
        f'{DEV} del int swp10.666',
        f'{DEV} set int swp10 description= label= tags=[]',
    ]

    for work in work_to_do:
        work.do(cmd.nbapi)
