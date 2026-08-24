import pytest

from nbtools.command import ProcessMode
from nbtools.exceptions import (
    TargetCountMismatch,
    UnrecognisedItemOnSource, UnrecognisedItemOnTarget)
from nbtools.synccmd.migr_gw import MigrateGatewayCommand
from nbtools.types import DevIface, Hostname

from ..nbstub import FakeNetbox


VM = 'vm1.example.com'


def a_netbox_with_one_gateway(vmaddr='10.0.0.1/31', gwaddr='10.0.0.0/31'):
    """
    One VM on one /31, its gateway on leaf1:swp34.1234 in vrf-red

    The target port leaf3:swp8 exists and is bare: no subinterface on
    it yet. That is the plain case the recipe describes.
    """
    nb = FakeNetbox()
    nb.red = nb.add_vrf('vrf-red')

    leaf1 = nb.add_device('leaf1')
    nb.swp34 = nb.add_interface(leaf1, 'swp34')
    nb.sub = nb.add_interface(
        leaf1, 'swp34.1234', parent=nb.swp34, vrf=nb.red)

    leaf3 = nb.add_device('leaf3')
    nb.swp8 = nb.add_interface(leaf3, 'swp8')

    vm = nb.add_vm(VM)
    ens1 = nb.add_vm_interface(vm, 'ens1')
    nb.vmip = nb.add_ip(vmaddr, ens1, vrf=nb.red)
    nb.gwip = nb.add_ip(gwaddr, nb.sub, vrf=nb.red)

    return nb


def a_command(nb, *targets, vms=(VM,), delete_empty=False):
    cmd = MigrateGatewayCommand(nb)
    cmd.set_target_interfaces([DevIface(target) for target in targets])
    cmd.set_vms([Hostname(vm) for vm in vms])
    if delete_empty:
        cmd.set_delete_empty()
    cmd.set_quiet()
    return cmd


def plan_for(nb, *targets, **kwargs):
    return [str(work) for work in a_command(nb, *targets, **kwargs).plan()]


def test_a_bare_target_port_gets_the_subinterface_made():
    nb = a_netbox_with_one_gateway()

    assert plan_for(nb, 'leaf3:swp8') == [
        'leaf3 add int swp8.1234 vrf vrf-red',
        'leaf1:swp34.1234 del ip 10.0.0.0/31',
        'leaf3:swp8.1234 add ip 10.0.0.0/31',
    ]


def test_the_new_subinterface_hangs_off_the_target_port():
    nb = a_netbox_with_one_gateway()

    a_command(nb, 'leaf3:swp8').run(ProcessMode.YES)

    made = nb.dcim.interfaces.get(device_id=nb.swp8.device.id,
                                  name='swp8.1234')
    assert made.parent.id == nb.swp8.id
    assert made.vrf.id == nb.red.id
    assert made.type.value == 'virtual'


def test_the_gateway_ends_up_on_the_new_subinterface():
    nb = a_netbox_with_one_gateway()

    a_command(nb, 'leaf3:swp8').run(ProcessMode.YES)

    assert nb.where_is(nb.gwip) == 'leaf3:swp8.1234'


def test_the_vm_ip_itself_is_not_touched():
    "The VM move is someone else's job; only its gateway moves here"
    nb = a_netbox_with_one_gateway()

    a_command(nb, 'leaf3:swp8').run(ProcessMode.YES)

    assert nb.where_is(nb.vmip) == f'{VM}:ens1'


def test_the_gateway_is_found_from_either_half_of_the_slash_31():
    "10.0.0.0/31 is the VM here, so the gateway is the .1"
    nb = a_netbox_with_one_gateway(
        vmaddr='10.0.0.0/31', gwaddr='10.0.0.1/31')

    assert plan_for(nb, 'leaf3:swp8') == [
        'leaf3 add int swp8.1234 vrf vrf-red',
        'leaf1:swp34.1234 del ip 10.0.0.1/31',
        'leaf3:swp8.1234 add ip 10.0.0.1/31',
    ]


def test_an_ipv6_gateway_moves_on_its_127():
    nb = a_netbox_with_one_gateway(
        vmaddr='2001:db8::1/127', gwaddr='2001:db8::/127')

    assert plan_for(nb, 'leaf3:swp8') == [
        'leaf3 add int swp8.1234 vrf vrf-red',
        'leaf1:swp34.1234 del ip 2001:db8::/127',
        'leaf3:swp8.1234 add ip 2001:db8::/127',
    ]


def test_an_existing_subinterface_in_the_same_vrf_is_reused():
    nb = a_netbox_with_one_gateway()
    nb.add_interface(
        nb.swp8.device, 'swp8.1234', parent=nb.swp8, vrf=nb.red)

    assert plan_for(nb, 'leaf3:swp8') == [
        'leaf1:swp34.1234 del ip 10.0.0.0/31',
        'leaf3:swp8.1234 add ip 10.0.0.0/31',
    ]


def test_an_ip_already_on_the_target_subinterface_stays_there():
    "We add ours alongside; what is there is not ours to move"
    nb = a_netbox_with_one_gateway()
    theirs_iface = nb.add_interface(
        nb.swp8.device, 'swp8.1234', parent=nb.swp8, vrf=nb.red)
    theirs = nb.add_ip('10.9.9.0/31', theirs_iface, vrf=nb.red)

    a_command(nb, 'leaf3:swp8').run(ProcessMode.YES)

    assert nb.where_is(theirs) == 'leaf3:swp8.1234'
    assert nb.where_is(nb.gwip) == 'leaf3:swp8.1234'


def test_an_existing_subinterface_in_another_vrf_is_an_error():
    "The VLAN matches but the routing does not: someone must look"
    nb = a_netbox_with_one_gateway()
    blue = nb.add_vrf('vrf-blue')
    nb.add_interface(
        nb.swp8.device, 'swp8.1234', parent=nb.swp8, vrf=blue)

    with pytest.raises(UnrecognisedItemOnTarget):
        plan_for(nb, 'leaf3:swp8')


def test_a_second_run_over_the_same_vm_does_nothing():
    nb = a_netbox_with_one_gateway()
    a_command(nb, 'leaf3:swp8').run(ProcessMode.YES)

    assert plan_for(nb, 'leaf3:swp8') == []


def a_netbox_with_an_anycast_gateway():
    """
    One gateway address on two leaves, the way clone-interface leaves it

    leaf1:swp34.1234 and leaf2:swp34.1234 both hold 10.0.0.0/31, so
    there are two source ports and both copies have to move.
    """
    nb = a_netbox_with_one_gateway()

    leaf2 = nb.add_device('leaf2')
    swp34 = nb.add_interface(leaf2, 'swp34')
    nb.sub2 = nb.add_interface(
        leaf2, 'swp34.1234', parent=swp34, vrf=nb.red)
    nb.gwip_clone = nb.add_ip('10.0.0.0/31', nb.sub2, vrf=nb.red)

    leaf4 = nb.add_device('leaf4')
    nb.add_interface(leaf4, 'swp8')

    return nb


def test_both_copies_of_an_anycast_gateway_move():
    nb = a_netbox_with_an_anycast_gateway()

    assert plan_for(nb, 'leaf3:swp8', 'leaf4:swp8') == [
        'leaf3 add int swp8.1234 vrf vrf-red',
        'leaf1:swp34.1234 del ip 10.0.0.0/31',
        'leaf3:swp8.1234 add ip 10.0.0.0/31',
        'leaf4 add int swp8.1234 vrf vrf-red',
        'leaf2:swp34.1234 del ip 10.0.0.0/31',
        'leaf4:swp8.1234 add ip 10.0.0.0/31',
    ]


def test_the_anycast_copies_end_up_one_on_each_target():
    nb = a_netbox_with_an_anycast_gateway()

    a_command(nb, 'leaf3:swp8', 'leaf4:swp8').run(ProcessMode.YES)

    assert nb.where_is(nb.gwip) == 'leaf3:swp8.1234'
    assert nb.where_is(nb.gwip_clone) == 'leaf4:swp8.1234'


def test_a_same_address_gateway_in_another_vrf_is_left_alone():
    "The same /31 is reused in every VRF; only ours moves"
    nb = a_netbox_with_one_gateway()
    blue = nb.add_vrf('vrf-blue')
    leaf2 = nb.add_device('leaf2')
    swp34 = nb.add_interface(leaf2, 'swp34')
    theirs_iface = nb.add_interface(
        leaf2, 'swp34.9999', parent=swp34, vrf=blue)
    theirs = nb.add_ip('10.0.0.0/31', theirs_iface, vrf=blue)

    # One source port, so one --target: the blue copy is not counted.
    a_command(nb, 'leaf3:swp8').run(ProcessMode.YES)

    assert nb.where_is(nb.gwip) == 'leaf3:swp8.1234'
    assert nb.where_is(theirs) == 'leaf2:swp34.9999'


def test_a_gateway_outside_any_vrf_moves_too():
    "Not every IP has a VRF, and the global table matches itself"
    nb = a_netbox_with_one_gateway()
    nb.vmip.vrf = nb.gwip.vrf = nb.sub.vrf = None

    assert plan_for(nb, 'leaf3:swp8') == [
        'leaf3 add int swp8.1234 vrf -',
        'leaf1:swp34.1234 del ip 10.0.0.0/31',
        'leaf3:swp8.1234 add ip 10.0.0.0/31',
    ]


def test_a_gateway_only_in_another_vrf_is_an_error():
    "Not ours to move, and nothing of ours to move either"
    nb = a_netbox_with_one_gateway()
    nb.gwip.vrf = nb.add_vrf('vrf-blue')

    with pytest.raises(UnrecognisedItemOnSource):
        plan_for(nb, 'leaf3:swp8')


def a_netbox_with_two_gateways():
    """
    A dual-homed VM: one /31 to leaf1, another to leaf2

    Two source ports, so two --targets, paired in sorted order.
    """
    nb = a_netbox_with_one_gateway()

    leaf2 = nb.add_device('leaf2')
    swp34 = nb.add_interface(leaf2, 'swp34')
    nb.sub2 = nb.add_interface(
        leaf2, 'swp34.2345', parent=swp34, vrf=nb.red)

    leaf4 = nb.add_device('leaf4')
    nb.add_interface(leaf4, 'swp8')

    vm = nb.virtualization.virtual_machines.get(name=VM)
    ens2 = nb.add_vm_interface(vm, 'ens2')
    nb.vmip2 = nb.add_ip('10.0.0.3/31', ens2, vrf=nb.red)
    nb.gwip2 = nb.add_ip('10.0.0.2/31', nb.sub2, vrf=nb.red)

    return nb


def test_targets_pair_with_the_source_ports_in_sorted_order():
    nb = a_netbox_with_two_gateways()

    assert plan_for(nb, 'leaf3:swp8', 'leaf4:swp8') == [
        'leaf3 add int swp8.1234 vrf vrf-red',
        'leaf1:swp34.1234 del ip 10.0.0.0/31',
        'leaf3:swp8.1234 add ip 10.0.0.0/31',
        'leaf4 add int swp8.2345 vrf vrf-red',
        'leaf2:swp34.2345 del ip 10.0.0.2/31',
        'leaf4:swp8.2345 add ip 10.0.0.2/31',
    ]


def test_the_pairing_follows_the_target_order_as_given():
    "Second --target first: the operator says which port goes where"
    nb = a_netbox_with_two_gateways()

    a_command(nb, 'leaf4:swp8', 'leaf3:swp8').run(ProcessMode.YES)

    assert nb.where_is(nb.gwip) == 'leaf4:swp8.1234'
    assert nb.where_is(nb.gwip2) == 'leaf3:swp8.2345'


def test_one_target_for_two_source_ports_is_an_error():
    nb = a_netbox_with_two_gateways()

    with pytest.raises(TargetCountMismatch):
        plan_for(nb, 'leaf3:swp8')


def test_two_targets_for_one_source_port_is_an_error():
    nb = a_netbox_with_one_gateway()
    leaf4 = nb.add_device('leaf4')
    nb.add_interface(leaf4, 'swp8')

    with pytest.raises(TargetCountMismatch):
        plan_for(nb, 'leaf3:swp8', 'leaf4:swp8')


def test_no_target_at_all_is_an_error():
    nb = a_netbox_with_one_gateway()

    with pytest.raises(TargetCountMismatch):
        plan_for(nb)


def test_two_vms_on_one_port_move_together():
    "One --target takes a whole port's worth, whichever VMs it serves"
    nb = a_netbox_with_one_gateway()
    vm2 = nb.add_vm('vm2.example.com')
    ens1 = nb.add_vm_interface(vm2, 'ens1')
    nb.add_ip('10.0.1.1/31', ens1, vrf=nb.red)
    gwip2 = nb.add_ip('10.0.1.0/31', nb.sub, vrf=nb.red)

    plan = plan_for(nb, 'leaf3:swp8', vms=(VM, 'vm2.example.com'))

    # One create, not two, for the subinterface they share.
    assert plan == [
        'leaf3 add int swp8.1234 vrf vrf-red',
        'leaf1:swp34.1234 del ip 10.0.0.0/31',
        'leaf3:swp8.1234 add ip 10.0.0.0/31',
        'leaf1:swp34.1234 del ip 10.0.1.0/31',
        'leaf3:swp8.1234 add ip 10.0.1.0/31',
    ]
    assert gwip2 in nb.ipam.ip_addresses.records


def test_delete_empty_removes_the_source_subinterface():
    nb = a_netbox_with_one_gateway()

    assert plan_for(nb, 'leaf3:swp8', delete_empty=True) == [
        'leaf3 add int swp8.1234 vrf vrf-red',
        'leaf1:swp34.1234 del ip 10.0.0.0/31',
        'leaf3:swp8.1234 add ip 10.0.0.0/31',
        'leaf1 del int swp34.1234',
    ]


def test_delete_empty_runs_after_the_ips_have_moved():
    nb = a_netbox_with_one_gateway()

    a_command(nb, 'leaf3:swp8', delete_empty=True).run(ProcessMode.YES)

    assert nb.where_is(nb.gwip) == 'leaf3:swp8.1234'
    assert nb.dcim.interfaces.deleted == [nb.sub.id]


def test_delete_empty_leaves_a_subinterface_that_keeps_an_ip():
    nb = a_netbox_with_one_gateway()
    nb.add_ip('10.5.5.0/31', nb.sub, vrf=nb.red)

    assert plan_for(nb, 'leaf3:swp8', delete_empty=True) == [
        'leaf3 add int swp8.1234 vrf vrf-red',
        'leaf1:swp34.1234 del ip 10.0.0.0/31',
        'leaf3:swp8.1234 add ip 10.0.0.0/31',
    ]


def test_delete_empty_waits_for_the_last_vm_to_leave():
    "Two VMs share the subinterface: it is empty only once both moved"
    nb = a_netbox_with_one_gateway()
    vm2 = nb.add_vm('vm2.example.com')
    ens1 = nb.add_vm_interface(vm2, 'ens1')
    nb.add_ip('10.0.1.1/31', ens1, vrf=nb.red)
    nb.add_ip('10.0.1.0/31', nb.sub, vrf=nb.red)

    # Only one of the two named: the other's gateway stays behind.
    assert 'leaf1 del int swp34.1234' not in plan_for(
        nb, 'leaf3:swp8', delete_empty=True)

    # Both named: nothing is left on it.
    assert 'leaf1 del int swp34.1234' in plan_for(
        nb, 'leaf3:swp8', vms=(VM, 'vm2.example.com'), delete_empty=True)


def test_without_the_flag_the_empty_source_subinterface_stays():
    nb = a_netbox_with_one_gateway()

    a_command(nb, 'leaf3:swp8').run(ProcessMode.YES)

    assert nb.dcim.interfaces.deleted == []
    assert nb.dcim.interfaces.get(nb.sub.id) is not None


def test_a_vm_ip_that_is_not_point_to_point_is_an_error():
    "The scheme is /31 gateways; a /24 has no 'other address'"
    nb = a_netbox_with_one_gateway(
        vmaddr='10.0.0.1/24', gwaddr='10.0.0.0/31')

    with pytest.raises(UnrecognisedItemOnSource):
        plan_for(nb, 'leaf3:swp8')


def test_a_gateway_that_netbox_does_not_hold_is_an_error():
    nb = a_netbox_with_one_gateway()
    nb.ipam.ip_addresses.records.remove(nb.gwip)

    with pytest.raises(UnrecognisedItemOnSource):
        plan_for(nb, 'leaf3:swp8')


def test_a_gateway_on_a_bare_port_is_an_error():
    "There is no .1234 to carry over to the target port"
    nb = a_netbox_with_one_gateway()
    nb.gwip.assigned_object = nb.swp34

    with pytest.raises(UnrecognisedItemOnSource):
        plan_for(nb, 'leaf3:swp8')


def test_a_gateway_on_a_vm_interface_is_an_error():
    "A gateway lives on a switch; this one is another VM's address"
    nb = a_netbox_with_one_gateway()
    nb.gwip.assigned_object_type = 'virtualization.vminterface'

    with pytest.raises(UnrecognisedItemOnSource):
        plan_for(nb, 'leaf3:swp8')


def test_an_unknown_target_port_is_an_error():
    nb = a_netbox_with_one_gateway()

    with pytest.raises(UnrecognisedItemOnTarget):
        plan_for(nb, 'leaf3:swp99')
