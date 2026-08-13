import pytest

from nbtools.synccmd.zap_macs import ZapMacAddressCommand
from nbtools.exceptions import UnrecognisedItem
from nbtools.types import MacAddr

from ..test_dup_macs import BMC, a_mac, an_iface, an_nbapi


def deleting_nbapi(*macs):
    "As an_nbapi, but recording what gets deleted"
    nbapi = an_nbapi(*macs)
    nbapi.deleted = []
    nbapi.dcim.mac_addresses.delete = nbapi.deleted.append
    return nbapi


def plan_for(nbapi, *macs):
    cmd = ZapMacAddressCommand(nbapi)
    cmd.set_mac_addresses([MacAddr(mac) for mac in macs])
    return cmd.plan()


def test_plans_a_delete_for_the_unassigned_copy():
    nbapi = deleting_nbapi(
        a_mac(1, 'AA:BB:CC:00:00:01', BMC),
        a_mac(2, 'AA:BB:CC:00:00:01'))

    assert [str(work) for work in plan_for(nbapi, 'AA:BB:CC:00:00:01')] == [
        'del mac aa:bb:cc:00:00:01 #2 (keeping #1 node1.example.com:BMC)']


def test_plans_nothing_when_every_copy_is_assigned():
    nbapi = deleting_nbapi(a_mac(1, 'AA:BB:CC:00:00:01', BMC))

    assert plan_for(nbapi, 'AA:BB:CC:00:00:01') == []


def test_takes_several_macs_at_once():
    "So a whole nblint --porcelain run is one plan and one confirmation"
    nbapi = deleting_nbapi(
        a_mac(1, 'AA:BB:CC:00:00:01', BMC),
        a_mac(2, 'AA:BB:CC:00:00:01'),
        a_mac(3, 'AA:BB:CC:00:00:09', BMC),
        a_mac(4, 'AA:BB:CC:00:00:09'))

    work = plan_for(nbapi, 'AA:BB:CC:00:00:01', 'AA:BB:CC:00:00:09')
    assert [str(future) for future in work] == [
        'del mac aa:bb:cc:00:00:01 #2 (keeping #1 node1.example.com:BMC)',
        'del mac aa:bb:cc:00:00:09 #4 (keeping #3 node1.example.com:BMC)',
    ]


def test_deletes_the_last_copy_when_nothing_is_assigned():
    "Named on the command line is the operator saying so"
    nbapi = deleting_nbapi(
        a_mac(1, 'AA:BB:CC:00:00:01'),
        a_mac(2, 'AA:BB:CC:00:00:01'))

    assert [str(work) for work in plan_for(nbapi, 'AA:BB:CC:00:00:01')] == [
        'del mac aa:bb:cc:00:00:01 #1',
        'del mac aa:bb:cc:00:00:01 #2',
    ]


def test_names_every_assigned_copy_it_keeps():
    "Two assigned copies is its own mess, but say so rather than hide it"
    other = an_iface('BMC', 'node2.example.com')
    nbapi = deleting_nbapi(
        a_mac(1, 'AA:BB:CC:00:00:01', BMC),
        a_mac(2, 'AA:BB:CC:00:00:01', other),
        a_mac(3, 'AA:BB:CC:00:00:01'))

    assert [str(work) for work in plan_for(nbapi, 'AA:BB:CC:00:00:01')] == [
        'del mac aa:bb:cc:00:00:01 #3 (keeping '
        '#1 node1.example.com:BMC, #2 node2.example.com:BMC)',
    ]


def test_an_unknown_mac_is_an_error():
    "Rather than quietly doing nothing, halfway through a batch"
    nbapi = deleting_nbapi(a_mac(1, 'AA:BB:CC:00:00:01', BMC))

    with pytest.raises(UnrecognisedItem):
        plan_for(nbapi, 'AA:BB:CC:00:00:99')


def test_a_near_miss_does_not_count_as_a_match():
    "The q= search is freeform, so it also returns neighbours"
    nbapi = deleting_nbapi(
        a_mac(1, 'AA:BB:CC:00:00:01', BMC),
        a_mac(2, 'AA:BB:CC:00:00:01'),
        a_mac(3, 'AA:BB:CC:00:00:12'))

    assert [str(work) for work in plan_for(nbapi, 'AA:BB:CC:00:00:01')] == [
        'del mac aa:bb:cc:00:00:01 #2 (keeping #1 node1.example.com:BMC)']


def test_executing_the_plan_deletes_by_id():
    nbapi = deleting_nbapi(
        a_mac(1, 'AA:BB:CC:00:00:01', BMC),
        a_mac(2, 'AA:BB:CC:00:00:01'))

    for future in plan_for(nbapi, 'AA:BB:CC:00:00:01'):
        future.do(nbapi)

    assert nbapi.deleted == [[2]]
