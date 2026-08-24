import pytest

from nbtools.types import DevIface, Hostname


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
