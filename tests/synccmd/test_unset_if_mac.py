import pytest

from nbtools.exceptions import UnrecognisedItem, UnrecognisedItemOnTarget
from nbtools.synccmd.unset_if_mac import UnsetInterfaceMacCommand
from nbtools.types import DevIface, MacAddr

from ..nbstub import a_mac, an_iface, an_nbapi


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
