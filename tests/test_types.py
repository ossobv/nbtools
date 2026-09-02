from ipaddress import IPv4Network, IPv6Network

import pytest

from nbtools.types import DevIface, Hostname, VrfPrefix


def test_dev_iface_splits_device_from_interface():
    assert DevIface('leaf1:eth0') == ('leaf1', 'eth0')


def test_dev_iface_renders_back_the_way_it_was_given():
    assert str(DevIface('leaf1:eth0')) == 'leaf1:eth0'


def test_dev_iface_allows_a_colon_in_the_device_name():
    "Real NetBox device names hold them; interface names do not"
    devif = DevIface('FREE (was-planned: node3.example.com):BMC')

    assert devif.device == 'FREE (was-planned: node3.example.com)'
    assert devif.interface == 'BMC'


def test_dev_iface_needs_a_colon():
    with pytest.raises(ValueError):
        DevIface('noseparator')


def test_dev_iface_none_is_the_empty_interface():
    assert DevIface.NONE == ('', '')
    assert DevIface(':') == DevIface.NONE
    assert str(DevIface.NONE) == ':'


def test_dev_iface_none_is_not_spelled_empty():
    "An unset shell variable must not become DevIface.NONE"
    with pytest.raises(ValueError):
        DevIface('')


def test_hostname_is_the_name_it_was_given():
    assert Hostname('vm1.example.com') == 'vm1.example.com'


def test_hostname_is_a_str_so_it_goes_into_a_filter_unchanged():
    assert isinstance(Hostname('vm1.example.com'), str)


def test_hostname_refuses_the_empty_name():
    with pytest.raises(ValueError):
        Hostname('')


def test_hostname_refuses_a_name_with_whitespace():
    "A shell quoting mistake, not a host"
    with pytest.raises(ValueError):
        Hostname('vm1.example.com vm2.example.com')


def test_vrf_prefix_splits_the_prefix_from_the_vrf():
    assert VrfPrefix('10.1.2.0/24@vrf-red') == (
        IPv4Network('10.1.2.0/24'), 'vrf-red')


def test_vrf_prefix_without_a_vrf_is_the_global_table():
    "'10.1.2.0/24' and '10.1.2.0/24@' are the same thing"
    assert VrfPrefix('10.1.2.0/24').vrf == ''
    assert VrfPrefix('10.1.2.0/24@').vrf == ''


def test_vrf_prefix_renders_back_as_it_was_argued():
    for text in ('10.1.2.0/24@vrf-red', '10.1.2.0/24@', '2001:db8::/64@a'):
        assert str(VrfPrefix(text)) == text


def test_vrf_prefix_renders_a_bare_prefix_with_the_empty_vrf():
    assert str(VrfPrefix('10.1.2.0/24')) == '10.1.2.0/24@'


def test_vrf_prefix_normalises_a_prefix_off_its_own_boundary():
    "NetBox stores what it was given; 10.1.2.1/24 is that same record"
    assert str(VrfPrefix('10.1.2.1/24@vrf-red')) == '10.1.2.0/24@vrf-red'


def test_vrf_prefix_splits_on_the_first_at():
    "A prefix never holds one; a VRF name might"
    assert VrfPrefix('10.1.2.0/24@odd@name').vrf == 'odd@name'


def test_vrf_prefix_takes_ipv6():
    assert VrfPrefix('2001:db8::/64@vrf-red').prefix == (
        IPv6Network('2001:db8::/64'))


def test_vrf_prefix_refuses_something_that_is_not_a_prefix():
    for text in ('', 'nonsense', 'nonsense@vrf-red', '@vrf-red',
                 '10.1.2.0/99@vrf-red'):
        with pytest.raises(ValueError):
            VrfPrefix(text)
