from nbtools.synccmd.set_if_ip import (
    SetInterfaceIpByMacCommand, SetInterfaceIpCommand)
from nbtools.types import DevIface, IPv4AddrWithMask, MacAddr

from ..nbtest import get_test_api, nb_responses_load


# The MACs as they appear in the recordings, and the devices they
# resolve to. The three recordings run in sequence: .65 starts on
# MBD-7, is forced onto node1, and is forced back again.
NODE1_MAC = '7C:C2:55:06:E7:61'         # BMC on node1..., interface 5319
MBD7_MAC = '7C:C2:55:0C:00:FA'          # BMC on MBD-7, interface 5325

NODE1_BMC = 'node1.zone-a.endor.example.com:BMC'
MBD7_BMC = 'MBD-7:BMC'


def make_command(mac, ip, **kwargs):
    set_if_ip = SetInterfaceIpByMacCommand(get_test_api())
    set_if_ip.set_target_interface_by_mac(MacAddr(mac))
    set_if_ip.set_ip(IPv4AddrWithMask(ip), **kwargs)
    return set_if_ip


def make_dev_command(devif, ip, **kwargs):
    "As make_command, but naming the target as DEV:IFACE"
    set_if_ip = SetInterfaceIpCommand(get_test_api())
    set_if_ip.set_target_interface(DevIface(devif))
    set_if_ip.set_ip(IPv4AddrWithMask(ip), **kwargs)
    return set_if_ip


def do_work(set_if_ip, work):
    "Execute the plan, so the recording checks the request bodies"
    for future in work:
        future.do(set_if_ip.nbapi)


@nb_responses_load('test_set_if_ip.simple-add.json', caller=__file__)
def test_set_if_ip_simple_add():
    """
    nbsync set-interface-ip node1.zone-a.endor.example.com:BMC
        10.103.1.64/24 --status=dhcp

    The plain case: the IP is nowhere in NetBox yet, so it is created
    on the named interface. This is also the only test that names its
    target as DEV:IFACE rather than by MAC, and the only one without
    --vrf, so the IP is created outside any VRF ('vrf -' below, null
    on the wire).
    """
    set_if_ip = make_dev_command(
        f'{NODE1_BMC}', '10.103.1.64/24', status='dhcp')

    work = set_if_ip.plan()
    assert [str(future) for future in work] == [
        f'{NODE1_BMC} add ip 10.103.1.64/24 vrf -',
    ]

    do_work(set_if_ip, work)


@nb_responses_load('test_set_if_ip.no-change.json', caller=__file__)
def test_set_if_ip_by_mac_no_change():
    r"""
    nbsync set-interface-ip-by-mac 7C:C2:55:06:E7:61 10.103.1.64/24 \
        --vrf=MGMT --status=dhcp

    The IP already sits on the interface the MAC belongs to, with that
    status and that VRF, so there is nothing left to do.
    """
    set_if_ip = make_command(
        NODE1_MAC, '10.103.1.64/24', status='dhcp', vrf='MGMT')

    assert set_if_ip.plan() == []


@nb_responses_load('test_set_if_ip.force-add.json', caller=__file__)
def test_set_if_ip_by_mac_force_add():
    r"""
    nbsync set-interface-ip-by-mac 7C:C2:55:06:E7:61 10.103.1.65/24 \
        --vrf=MGMT --status=dhcp --force

    The IP is in use on MBD-7, so --force takes it away and reassigns
    it here. The .64 address already on this interface is left alone;
    removing that would take --single.
    """
    set_if_ip = make_command(
        NODE1_MAC, '10.103.1.65/24', status='dhcp', vrf='MGMT', force=True)

    work = set_if_ip.plan()
    assert [str(future) for future in work] == [
        # No API call of its own; it shows where the IP is taken from.
        f'{MBD7_BMC} del ip 10.103.1.65/24',
        f'{NODE1_BMC} add ip 10.103.1.65/24 vrf MGMT',
        # NOTE: The reassign above already sets status and vrf, so this
        # last one is a second PATCH with nothing new in it. It happens
        # because the force branch moves the IP into good_ips, and the
        # status/VRF check at the end then compares against the record
        # as it was fetched, i.e. before the reassign. Contrast
        # test_set_if_ip_by_mac_force_single below, where the IP
        # already has the wanted status and no such PATCH appears.
        f'{NODE1_BMC} set ip 10.103.1.65/24 status=dhcp vrf=MGMT',
    ]

    do_work(set_if_ip, work)


@nb_responses_load('test_set_if_ip.force-single.json', caller=__file__)
def test_set_if_ip_by_mac_force_single():
    r"""
    nbsync set-interface-ip-by-mac 7C:C2:55:0C:00:FA 10.103.1.65/24 \
        --vrf=MGMT --status=dhcp --force --single

    The reverse of the previous test: .65 is forced back to MBD-7. This
    time --single is given, so the .251 address that MBD-7 was holding
    is deleted rather than left in place.
    """
    set_if_ip = make_command(
        MBD7_MAC, '10.103.1.65/24', status='dhcp', vrf='MGMT',
        force=True, single=True)

    work = set_if_ip.plan()
    assert [str(future) for future in work] == [
        f'{NODE1_BMC} del ip 10.103.1.65/24',
        f'{MBD7_BMC} add ip 10.103.1.65/24 vrf MGMT',
        # --single: this one was already here and is not the IP we want.
        f'{MBD7_BMC} del ip 10.103.1.251/24',
    ]

    do_work(set_if_ip, work)
