import io
import sys

from argparse import ArgumentParser

import pytest

from nbtools.command import ProcessMode, STDIN_ARG
from nbtools.exceptions import (
    InvalidInput, UnrecognisedItem, UnrecognisedItemOnTarget)
from nbtools.synccmd.unset_if_mac import UnsetInterfaceMacCommand
from nbtools.types import DevIface, MacAddr

from ..nbstub import a_mac, a_vm_iface, an_iface, an_nbapi


BMC = an_iface('BMC', 'node1.example.com')
MAC = 'AA:BB:CC:00:00:01'


def plan_for(nbapi, target, *macs):
    cmd = UnsetInterfaceMacCommand(nbapi)
    cmd.set_target_interface(DevIface(target))
    cmd.set_mac_addresses([MacAddr(mac) for mac in macs])
    return cmd.plan()


def test_the_empty_target_takes_the_unassigned_copy():
    nbapi = an_nbapi(a_mac(1, MAC, BMC), a_mac(2, MAC), iface=BMC)

    assert [str(work) for work in plan_for(nbapi, ':', MAC)] == [
        ': del mac aa:bb:cc:00:00:01']


def test_the_empty_target_leaves_assigned_copies_alone():
    nbapi = an_nbapi(a_mac(1, MAC, BMC), iface=BMC)

    assert plan_for(nbapi, ':', MAC) == []


def test_the_empty_target_takes_every_unassigned_copy():
    "There is no last-copy rule: the operator named the MAC"
    nbapi = an_nbapi(a_mac(1, MAC), a_mac(2, MAC))

    assert [str(work) for work in plan_for(nbapi, ':', MAC)] == [
        ': del mac aa:bb:cc:00:00:01',
        ': del mac aa:bb:cc:00:00:01',
    ]


def test_a_real_target_takes_the_copy_that_is_on_it():
    nbapi = an_nbapi(a_mac(1, MAC, BMC), a_mac(2, MAC), iface=BMC)

    assert [str(work) for work in plan_for(
        nbapi, 'node1.example.com:BMC', MAC)] == [
        'node1.example.com:BMC del mac aa:bb:cc:00:00:01']


def test_a_real_target_quotes_a_device_name_with_spaces():
    "A real NetBox device name, holding both a space and a colon"
    spaced = an_iface('BMC', 'FREE (was-planned: node3.example.com)')
    nbapi = an_nbapi(a_mac(1, MAC, spaced), iface=spaced)

    assert [str(work) for work in plan_for(
        nbapi, 'FREE (was-planned: node3.example.com):BMC', MAC)] == [
        "'FREE (was-planned: node3.example.com)':BMC "
        'del mac aa:bb:cc:00:00:01']


def test_a_copy_on_another_interface_is_left_alone():
    other = an_iface('BMC', 'node2.example.com', id_=9999)
    nbapi = an_nbapi(a_mac(1, MAC, BMC), a_mac(2, MAC, other), iface=BMC)

    assert [str(work) for work in plan_for(
        nbapi, 'node1.example.com:BMC', MAC)] == [
        'node1.example.com:BMC del mac aa:bb:cc:00:00:01']


def test_a_vm_interface_with_the_same_id_is_not_the_target():
    "vminterface ids come from another table than dcim interface ids"
    same_id = a_vm_iface('eth0', 'vm1.example.com', id_=BMC.id)
    nbapi = an_nbapi(a_mac(1, MAC, same_id), iface=BMC)

    assert plan_for(nbapi, 'node1.example.com:BMC', MAC) == []


def test_a_vm_interface_does_not_count_as_unassigned_either():
    vm_iface = a_vm_iface('eth0', 'vm1.example.com')
    nbapi = an_nbapi(a_mac(1, MAC, vm_iface))

    assert plan_for(nbapi, ':', MAC) == []


def test_takes_several_macs_at_once():
    "So a whole run is one plan and one confirmation"
    other = 'AA:BB:CC:00:00:09'
    nbapi = an_nbapi(
        a_mac(1, MAC, BMC), a_mac(2, MAC),
        a_mac(3, other, BMC), a_mac(4, other))

    assert [str(work) for work in plan_for(nbapi, ':', MAC, other)] == [
        ': del mac aa:bb:cc:00:00:01',
        ': del mac aa:bb:cc:00:00:09',
    ]


def test_an_unknown_mac_is_an_error():
    "Rather than quietly doing nothing, halfway through a batch"
    nbapi = an_nbapi(a_mac(1, MAC, BMC))

    with pytest.raises(UnrecognisedItem):
        plan_for(nbapi, ':', 'AA:BB:CC:00:00:99')


def test_an_unknown_target_is_an_error():
    nbapi = an_nbapi(a_mac(1, MAC, BMC), iface=None)

    with pytest.raises(UnrecognisedItemOnTarget):
        plan_for(nbapi, 'nosuch.example.com:BMC', MAC)


def test_a_near_miss_does_not_count_as_a_match():
    "The q= search is freeform, so it also returns neighbours"
    nbapi = an_nbapi(
        a_mac(1, MAC, BMC), a_mac(2, MAC), a_mac(3, 'AA:BB:CC:00:00:012'),
        iface=BMC)

    assert [str(work) for work in plan_for(nbapi, ':', MAC)] == [
        ': del mac aa:bb:cc:00:00:01']


def test_executing_the_plan_deletes_by_id():
    nbapi = an_nbapi(a_mac(1, MAC, BMC), a_mac(2, MAC), iface=BMC)

    for work in plan_for(nbapi, ':', MAC):
        work.do(nbapi)

    assert nbapi.deleted == [[2]]


# -- stdin --

OTHER = 'AA:BB:CC:00:00:09'


def parse_args(argv):
    parser = ArgumentParser()
    UnsetInterfaceMacCommand.add_arguments(parser)
    return parser.parse_args(argv)


def a_streaming_command(nbapi, monkeypatch, argv, stdin):
    monkeypatch.setattr(sys, 'stdin', io.StringIO(stdin))
    return UnsetInterfaceMacCommand.from_args(nbapi, parse_args(argv))


def test_a_dash_gets_past_argparse():
    "'-' is not a DEV:IFACE and not a MAC, so stdin_or() lets it by"
    args = parse_args([STDIN_ARG, STDIN_ARG])

    assert (args.target, args.mac) == (STDIN_ARG, [STDIN_ARG])


def test_the_macs_come_off_stdin_for_the_one_target(monkeypatch, capsys):
    "nblint --porcelain duplicate-macs | nbsync unset-interface-mac : -"
    nbapi = an_nbapi(
        a_mac(1, MAC, BMC), a_mac(2, MAC), a_mac(3, OTHER), iface=BMC)
    cmd = a_streaming_command(
        nbapi, monkeypatch, [':', STDIN_ARG], f'{MAC}\n{OTHER}\n')

    assert cmd.run(ProcessMode.YES) == 0
    assert capsys.readouterr().out == (
        '- : del mac aa:bb:cc:00:00:01\n'
        '- : del mac aa:bb:cc:00:00:09\n')
    assert nbapi.deleted == [[2], [3]]


def test_a_typed_mac_goes_before_the_stream(monkeypatch, capsys):
    nbapi = an_nbapi(a_mac(2, MAC), a_mac(3, OTHER))
    cmd = a_streaming_command(
        nbapi, monkeypatch, [':', OTHER, STDIN_ARG], f'{MAC}\n')

    assert cmd.run(ProcessMode.YES) == 0
    assert nbapi.deleted == [[3], [2]]


def test_a_line_holds_the_target_then_the_mac(monkeypatch, capsys):
    nbapi = an_nbapi(a_mac(1, MAC, BMC), a_mac(2, OTHER), iface=BMC)
    cmd = a_streaming_command(
        nbapi, monkeypatch, [STDIN_ARG, STDIN_ARG],
        f'node1.example.com:BMC {MAC}\n: {OTHER}\n')

    assert cmd.run(ProcessMode.YES) == 0
    assert capsys.readouterr().out == (
        '- node1.example.com:BMC del mac aa:bb:cc:00:00:01\n'
        '- : del mac aa:bb:cc:00:00:09\n')
    assert nbapi.deleted == [[1], [2]]


def test_a_typed_mac_is_taken_off_every_target_read(monkeypatch):
    nbapi = an_nbapi(a_mac(1, MAC, BMC), a_mac(2, MAC), iface=BMC)
    cmd = a_streaming_command(
        nbapi, monkeypatch, [STDIN_ARG, MAC], 'node1.example.com:BMC\n:\n')

    assert cmd.run(ProcessMode.YES) == 0
    assert nbapi.deleted == [[1], [2]]


def test_several_macs_beside_a_target_on_stdin_are_refused():
    with pytest.raises(InvalidInput, match='one MAC'):
        UnsetInterfaceMacCommand.from_args(
            an_nbapi(), parse_args([STDIN_ARG, MAC, OTHER]))


def test_stdin_input_needs_batch(monkeypatch):
    cmd = a_streaming_command(
        an_nbapi(a_mac(2, MAC)), monkeypatch, [':', STDIN_ARG], f'{MAC}\n')

    with pytest.raises(SystemExit):
        cmd.run(ProcessMode.INTERACTIVE)
