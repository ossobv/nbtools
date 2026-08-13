import pytest

from nbtools.types import DevIface


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
