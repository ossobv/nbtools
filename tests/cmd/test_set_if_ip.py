from nbtools.cmd.set_if_ip import SetInterfaceIpByMacCommand
from nbtools.types import IPv4AddrWithMask, MacAddr

from ..nbtest import get_test_api, nb_responses_load


# The MAC as it appears in the recordings. It resolves to BMC on
# node1.zone-a.endor.example.com (interface 5319).
MAC = '7C:C2:55:06:E7:61'
NODE1_BMC = 'node1.zone-a.endor.example.com:BMC'


def make_command(ip, **kwargs):
    set_if_ip = SetInterfaceIpByMacCommand(get_test_api())
    set_if_ip.set_target_interface_by_mac(MacAddr(MAC))
    set_if_ip.set_ip(IPv4AddrWithMask(ip), **kwargs)
    return set_if_ip


@nb_responses_load('test_set_if_ip.no-change.json', caller=__file__)
def test_set_if_ip_by_mac_no_change():
    r"""
    nbsync set-interface-ip-by-mac 7C:C2:55:06:E7:61 10.103.1.64/24 \
        --vrf=MGMT --status=dhcp

    The IP already sits on the interface the MAC belongs to, with that
    status and that VRF, so there is nothing left to do.
    """
    set_if_ip = make_command('10.103.1.64/24', status='dhcp', vrf='MGMT')

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
        '10.103.1.65/24', status='dhcp', vrf='MGMT', force=True)

    work = set_if_ip.plan()
    assert [str(future) for future in work] == [
        # No API call of its own; it shows where the IP is taken from.
        'MBD-7:BMC del ip 10.103.1.65/24',
        f'{NODE1_BMC} add ip 10.103.1.65/24 vrf MGMT',
        # NOTE: The reassign above already sets status and vrf, so this
        # last one is a second PATCH with nothing new in it. It happens
        # because the force branch moves the IP into good_ips, and the
        # status/VRF check at the end then compares against the record
        # as it was _before_ the reassign.
        f'{NODE1_BMC} set ip 10.103.1.65/24 status=dhcp vrf=MGMT',
    ]

    # Run it too: the recording asserts the PATCH bodies for us.
    for future in work:
        future.do(set_if_ip.nbapi)
