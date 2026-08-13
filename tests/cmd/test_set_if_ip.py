from nbtools.cmd.set_if_ip import SetInterfaceIpByMacCommand
from nbtools.types import IPv4AddrWithMask, MacAddr

from ..nbtest import get_test_api, nb_responses_load


@nb_responses_load('test_set_if_ip.no-change.json', caller=__file__)
def test_set_if_ip_by_mac_no_change():
    r"""
    nbsync set-interface-ip-by-mac 7C:C2:55:06:E7:61 10.103.1.64/24 \
        --vrf=MGMT --status=dhcp

    The IP already sits on the interface the MAC belongs to, with that
    status and that VRF, so there is nothing left to do.
    """
    mac = MacAddr('7C:C2:55:06:E7:61')
    ip = IPv4AddrWithMask('10.103.1.64/24')

    set_if_ip = SetInterfaceIpByMacCommand(get_test_api())
    set_if_ip.set_target_interface_by_mac(mac)
    set_if_ip.set_ip(ip, status='dhcp', vrf='MGMT')

    assert set_if_ip.plan() == []
