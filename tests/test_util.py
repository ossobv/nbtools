from ipaddress import IPv4Interface

import pytest

from nbtools.util import (
    natsort_key, peer_address, quoted_name, split_subinterface)


# A real NetBox device name, shortened.
SPACED_DEV = 'FREE (was-planned: node3.example.com)'


def test_natsort_key():
    assert natsort_key('swp34.1234') == ('swp', 34, '.', 1234)


def test_quoted_name_leaves_plain_name_alone():
    assert quoted_name('node3.example.com') == 'node3.example.com'


def test_quoted_name_quotes_name_with_space():
    assert quoted_name(SPACED_DEV) == f"'{SPACED_DEV}'"


def test_quoted_name_doubles_embedded_quote():
    assert quoted_name("Bob's spare (old)") == "'Bob''s spare (old)'"


def test_quoted_name_quotes_on_a_quote_alone():
    "Else a leading quote reads as the start of a quoted name"
    assert quoted_name("'weird") == "'''weird'"


def test_quoted_name_leaves_backslash_alone():
    "Only the quote is special; a backslash needs no second rule"
    assert quoted_name('c:\\some path') == "'c:\\some path'"


def test_peer_address_of_the_lower_half_is_the_upper_one():
    assert str(peer_address('10.0.0.0/31')) == '10.0.0.1/31'


def test_peer_address_of_the_upper_half_is_the_lower_one():
    assert str(peer_address('10.0.0.1/31')) == '10.0.0.0/31'


def test_peer_address_crosses_the_octet_boundary():
    assert str(peer_address('10.0.0.255/31')) == '10.0.0.254/31'


def test_peer_address_does_ipv6_on_a_127():
    assert str(peer_address('2001:db8::1/127')) == '2001:db8::/127'


def test_peer_address_takes_whatever_renders_as_an_address():
    "NetBox hands back a str, argparse an IPv4Interface"
    assert str(peer_address(IPv4Interface('10.0.0.1/31'))) == '10.0.0.0/31'


def test_peer_address_refuses_a_wider_ipv4_subnet():
    "On a /24 there is no single other address to mean"
    with pytest.raises(ValueError):
        peer_address('10.0.0.1/24')


def test_peer_address_refuses_a_single_host():
    with pytest.raises(ValueError):
        peer_address('10.0.0.1/32')


def test_peer_address_refuses_a_64_for_ipv6():
    "The IPv6 point-to-point prefix is the /127, not the /31"
    with pytest.raises(ValueError):
        peer_address('2001:db8::1/64')


def test_split_subinterface_splits_a_numeric_suffix():
    assert split_subinterface('swp1.2107') == ('swp1', 2107)


def test_split_subinterface_returns_none_for_a_plain_interface():
    assert split_subinterface('swp1') is None
    assert split_subinterface('BMC') is None


def test_split_subinterface_wants_the_suffix_to_be_a_number():
    "'swp1.mgmt' is a name that happens to hold a dot"
    assert split_subinterface('swp1.mgmt') is None
    assert split_subinterface('swp1.') is None


def test_split_subinterface_splits_on_the_last_dot():
    "A dotted parent name is still a parent name"
    assert split_subinterface('swp1.2.3') == ('swp1.2', 3)


def test_split_subinterface_reads_the_number_as_base_ten():
    assert split_subinterface('swp1.007') == ('swp1', 7)
    assert split_subinterface('swp1.0x10') is None


def test_split_subinterface_takes_whatever_renders_as_a_name():
    "NetBox record names render through __str__, not always as str"
    class Name:
        def __str__(self):
            return 'swp1.2107'

    assert split_subinterface(Name()) == ('swp1', 2107)
