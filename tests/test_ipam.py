"""
The address arithmetic, with records built by hand.

ipam.py holds no nbapi, so these need no stub: a namespace with a
'prefix' or an 'address' on it is all the module ever looks at.
"""
from ipaddress import ip_network
from types import SimpleNamespace as NS

from nbtools.ipam import (
    GLOBAL_VRF, IpamIndex, address_of, network_of, prefixlen_of,
    status_name, vrf_id, vrf_name)


RED = NS(id=301, name='vrf-red')
BLUE = NS(id=302, name='vrf-blue')


def a_prefix(prefix, vrf=None, status='active'):
    return NS(
        id=None, prefix=prefix, vrf=vrf,
        status=NS(value=status, label=status.title()))


def an_ip(address, vrf=None, status='active'):
    return NS(
        id=None, address=address, vrf=vrf,
        status=NS(value=status, label=status.title()))


def test_vrf_of_a_record_without_one_is_the_global_table():
    assert vrf_id(a_prefix('10.0.0.0/24')) is None
    assert vrf_name(a_prefix('10.0.0.0/24')) == GLOBAL_VRF


def test_vrf_of_a_record_with_one():
    assert vrf_id(a_prefix('10.0.0.0/24', vrf=RED)) == 301
    assert vrf_name(a_prefix('10.0.0.0/24', vrf=RED)) == 'vrf-red'


def test_status_is_the_value_not_the_label():
    "'container' is what the operator filters on, 'Container' is not"
    assert status_name(a_prefix('10.0.0.0/8', status='container')) == (
        'container')


def test_status_of_a_record_that_has_none():
    assert status_name(NS(id=1)) == '-'


def test_network_of_a_prefix_recorded_off_its_own_boundary():
    "NetBox stores what it was given; 10.0.0.1/24 means 10.0.0.0/24"
    assert network_of(a_prefix('10.0.0.1/24')) == ip_network('10.0.0.0/24')


def test_address_drops_the_mask_and_prefixlen_keeps_it():
    ipaddr = an_ip('10.0.0.7/24')

    assert str(address_of(ipaddr)) == '10.0.0.7'
    assert prefixlen_of(ipaddr) == 24


def test_a_prefix_holding_nothing_is_empty():
    index = IpamIndex([a_prefix('10.0.0.0/24')], [])

    assert index.is_empty_prefix(a_prefix('10.0.0.0/24'))


def test_a_prefix_holding_an_address_is_not_empty():
    index = IpamIndex([a_prefix('10.0.0.0/24')], [an_ip('10.0.0.7/24')])

    assert not index.is_empty_prefix(a_prefix('10.0.0.0/24'))


def test_the_last_address_of_a_prefix_still_counts():
    "The range is inclusive at both ends"
    index = IpamIndex([a_prefix('10.0.0.0/24')], [an_ip('10.0.0.255/24')])

    assert not index.is_empty_prefix(a_prefix('10.0.0.0/24'))


def test_the_address_just_past_a_prefix_does_not_count():
    index = IpamIndex([a_prefix('10.0.0.0/24')], [an_ip('10.0.1.0/24')])

    assert index.is_empty_prefix(a_prefix('10.0.0.0/24'))


def test_a_prefix_holding_a_smaller_prefix_is_not_empty():
    "A container with children is doing its job, however few IPs it has"
    prefixes = [a_prefix('10.0.0.0/8'), a_prefix('10.1.2.0/24')]
    index = IpamIndex(prefixes, [])

    assert not index.is_empty_prefix(prefixes[0])
    assert index.is_empty_prefix(prefixes[1])


def test_a_prefix_is_not_its_own_child():
    index = IpamIndex([a_prefix('10.0.0.0/24')], [])

    assert index.is_empty_prefix(a_prefix('10.0.0.0/24'))


def test_the_same_prefix_twice_leaves_both_empty():
    "Two copies are a duplicate, not each other's children"
    prefixes = [a_prefix('10.0.0.0/24'), a_prefix('10.0.0.0/24')]
    index = IpamIndex(prefixes, [])

    assert index.is_empty_prefix(prefixes[0])
    assert index.is_empty_prefix(prefixes[1])


def test_another_vrf_does_not_fill_a_prefix():
    "A prefix in one VRF says nothing about an address in another"
    index = IpamIndex(
        [a_prefix('10.0.0.0/24', vrf=RED)],
        [an_ip('10.0.0.7/24', vrf=BLUE)])

    assert index.is_empty_prefix(a_prefix('10.0.0.0/24', vrf=RED))


def test_the_global_table_does_not_fill_a_vrf_prefix():
    index = IpamIndex(
        [a_prefix('10.0.0.0/24', vrf=RED)], [an_ip('10.0.0.7/24')])

    assert index.is_empty_prefix(a_prefix('10.0.0.0/24', vrf=RED))


def test_a_prefix_in_a_vrf_with_nothing_at_all_is_empty():
    index = IpamIndex([], [])

    assert index.is_empty_prefix(a_prefix('10.0.0.0/24', vrf=RED))


def test_ipv6_prefixes_and_addresses_do_not_mix_with_ipv4():
    "int(::) and int(0.0.0.0) are both 0, so the family is part of the key"
    index = IpamIndex(
        [a_prefix('10.0.0.0/24'), a_prefix('2001:db8::/64')],
        [an_ip('10.0.0.7/24')])

    assert index.is_empty_prefix(a_prefix('2001:db8::/64'))
    assert not index.is_empty_prefix(a_prefix('10.0.0.0/24'))


def test_an_ipv6_prefix_holding_an_address_is_not_empty():
    index = IpamIndex(
        [a_prefix('2001:db8::/64')], [an_ip('2001:db8::7/64')])

    assert not index.is_empty_prefix(a_prefix('2001:db8::/64'))


def test_covering_prefixlens_are_longest_first():
    index = IpamIndex([
        a_prefix('10.0.0.0/8'), a_prefix('10.0.0.0/16'),
        a_prefix('10.0.0.0/24')], [])

    assert index.covering_prefixlens(an_ip('10.0.0.7/24')) == [24, 16, 8]


def test_covering_prefixlens_stop_at_down_to():
    "Asking whether a /24 covers it has no use for the /8 that also does"
    index = IpamIndex([a_prefix('10.0.0.0/8'), a_prefix('10.0.0.0/24')], [])

    assert index.covering_prefixlens(an_ip('10.0.0.7/32'), down_to=24) == [24]


def test_covering_prefixlens_finds_a_host_prefix():
    index = IpamIndex([a_prefix('10.0.0.7/32')], [])

    assert index.covering_prefixlens(an_ip('10.0.0.7/24')) == [32]


def test_covering_prefixlens_ignores_the_recorded_mask():
    "10.0.0.7/32 is covered by a /24 whatever mask the record carries"
    index = IpamIndex([a_prefix('10.0.0.0/24')], [])

    assert index.covering_prefixlens(an_ip('10.0.0.7/32')) == [24]


def test_covering_prefixlens_of_an_address_in_an_unknown_vrf():
    index = IpamIndex([a_prefix('10.0.0.0/24')], [])

    assert index.covering_prefixlens(an_ip('10.0.0.7/24', vrf=RED)) == []


def test_covering_prefixlens_for_ipv6():
    index = IpamIndex([a_prefix('2001:db8::/64')], [])

    assert index.covering_prefixlens(
        an_ip('2001:db8::7/64'), down_to=64) == [64]
