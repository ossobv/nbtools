"""
Every registered command, over one NetBox.

This is the shape of an `nblint` run with no COMMAND: the tool builds
each class with nothing but an nbapi and calls run() on all of them. So
this catches the two things a per-command test cannot -- a command that
reads an endpoint nothing else touches, and one that only works when
from_args() has been through it first.
"""
import pytest

from nbtools.lintcmd import COMMANDS, COMMANDS_BY_NAME

from ..nbstub import FakeNetbox


def a_populated_netbox():
    "A small NetBox with one of everything the commands read"
    nb = FakeNetbox()

    red = nb.add_vrf('STAIRS')
    nb.add_prefix('10.1.2.0/24', vrf=red)

    leaf1 = nb.add_device('leaf1')
    leaf2 = nb.add_device('leaf2')
    swp1 = nb.add_interface(leaf1, 'swp1')
    sub = nb.add_interface(
        leaf1, 'swp1.1234', parent=swp1, vrf=red, label='STAIRS')
    nb.add_ip('10.1.2.7/24', iface=sub, vrf=red)

    bmc = nb.add_interface(leaf1, 'BMC', mgmt_only=True)
    nb.add_mac('AA:BB:CC:00:00:01', iface=bmc)

    # leaf2's BMC is the other kind: not named BMC at all, recognised
    # by being the interface the device's oob_ip sits on. Every device
    # needs one of the three, since device-bmcs reports a machine with
    # none of them -- and a BMC named BMC owes mgmt_only on top.
    nb.add_prefix('10.1.3.0/24')
    oob = nb.add_interface(leaf2, 'mgmt0')
    nb.add_mac('AA:BB:CC:00:00:02', iface=oob)
    nb.set_oob_ip(leaf2, nb.add_ip('10.1.3.7/24', iface=oob))

    nb.add_cable(
        nb.add_interface(leaf1, 'swp2', tags=['corelink']),
        nb.add_interface(leaf2, 'swp2', tags=['corelink']))

    nb.add_interface(
        leaf1, 'swp3', tags=['closso_roth'], mode='access',
        untagged_vlan=nb.add_vlan(100))

    # The cluster but nothing in it. discovered-items is a listing
    # rather than a fault check, so anything filed under Discovery is
    # a finding by design -- which is the point of the note in this
    # command's --help, and why a tidy NetBox has the cluster empty.
    nb.add_cluster('Discovery')
    nb.add_tenant('acme-bv', description='ACME B.V.')
    nb.add_tenant('resellers', group=True)

    return nb


@pytest.mark.parametrize(
    'name', sorted(COMMANDS_BY_NAME), ids=sorted(COMMANDS_BY_NAME))
def test_every_command_is_clean_on_a_tidy_netbox(name, capsys):
    "Built with nothing but an nbapi, the way a no-COMMAND run does"
    cmd = COMMANDS_BY_NAME[name](a_populated_netbox())

    assert cmd.run() == 0, capsys.readouterr().out


@pytest.mark.parametrize(
    'name', sorted(COMMANDS_BY_NAME), ids=sorted(COMMANDS_BY_NAME))
def test_every_command_survives_an_empty_netbox(name):
    assert COMMANDS_BY_NAME[name](FakeNetbox()).run() == 0


def test_every_command_has_a_name_and_a_help_text():
    for cmdcls in COMMANDS:
        assert cmdcls.name, cmdcls
        assert cmdcls.help, cmdcls


def test_the_names_are_unique():
    assert len(COMMANDS_BY_NAME) == len(COMMANDS)
