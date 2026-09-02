import io
import sys

from argparse import ArgumentParser

import responses

from nbtools.command import ProcessMode, STDIN_ARG
from nbtools.synccmd.set_if_ip import (
    SetInterfaceIpByMacCommand, SetInterfaceIpCommand, TargetIp)
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
    set_if_ip.set_input([TargetIp(MacAddr(mac), IPv4AddrWithMask(ip))])
    set_if_ip.set_options(**kwargs)
    return set_if_ip


def make_dev_command(devif, ip, **kwargs):
    "As make_command, but naming the target as DEV:IFACE"
    set_if_ip = SetInterfaceIpCommand(get_test_api())
    set_if_ip.set_input([TargetIp(DevIface(devif), IPv4AddrWithMask(ip))])
    set_if_ip.set_options(**kwargs)
    return set_if_ip


def make_streaming_command(lines, monkeypatch, **kwargs):
    "As make_command, but with the pairs arriving on stdin"
    monkeypatch.setattr(sys, 'stdin', io.StringIO(lines))
    set_if_ip = SetInterfaceIpByMacCommand(get_test_api())
    set_if_ip.set_input_rows(TargetIp, [
        (STDIN_ARG, MacAddr), (STDIN_ARG, IPv4AddrWithMask)])
    set_if_ip.set_options(**kwargs)
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


# -- the pairs arriving on stdin --

TWO_LINES = f'{NODE1_MAC} 10.103.1.64/24\n' * 2


@nb_responses_load('test_set_if_ip.no-change.json', caller=__file__)
def test_set_if_ip_by_mac_takes_the_pair_off_a_line(monkeypatch):
    r"""
    ... | nbsync --batch set-interface-ip-by-mac - - \
        --vrf=MGMT --status=dhcp

    The no-change item above, twice, arriving a line at a time
    instead of as arguments. Nothing to do, either way.
    """
    set_if_ip = make_streaming_command(
        TWO_LINES, monkeypatch, status='dhcp', vrf='MGMT')

    assert set_if_ip.run(ProcessMode.YES) == 0


@nb_responses_load('test_set_if_ip.no-change.json', caller=__file__)
def test_the_vrf_is_looked_up_once_for_the_whole_stream(monkeypatch):
    "It is an option, so it cannot change from line to line"
    set_if_ip = make_streaming_command(
        TWO_LINES, monkeypatch, status='dhcp', vrf='MGMT')
    set_if_ip.run(ProcessMode.YES)

    assert len([
        call for call in responses.calls
        if '/ipam/vrfs/' in call.request.url]) == 1


@nb_responses_load('test_set_if_ip.no-change.json', caller=__file__)
def test_the_mac_is_looked_up_per_line(monkeypatch):
    "That one does vary, so it cannot be hoisted the same way"
    set_if_ip = make_streaming_command(
        TWO_LINES, monkeypatch, status='dhcp', vrf='MGMT')
    set_if_ip.run(ProcessMode.YES)

    assert len([
        call for call in responses.calls
        if '/dcim/mac-addresses/' in call.request.url]) == 2


def parse_args(argv):
    "What nbsync's parser makes of these arguments"
    parser = ArgumentParser()
    SetInterfaceIpByMacCommand.add_arguments(parser)
    return parser.parse_args(argv)


def test_a_dash_per_argument_gets_past_argparse():
    "'-' is not a MAC and not an IP, so stdin_or() has to let it by"
    args = parse_args([STDIN_ARG, STDIN_ARG, '--vrf=MGMT'])

    assert (args.target, args.ip) == (STDIN_ARG, STDIN_ARG)


def test_a_line_holds_the_target_then_the_ip(monkeypatch):
    "The order they are typed in, which is the order argparse has"
    set_if_ip = make_streaming_command('', monkeypatch)
    row = set_if_ip._parse_row(f'{NODE1_MAC} 10.103.1.64/24')

    assert (str(row.target), str(row.ip)) == (
        NODE1_MAC.lower(), '10.103.1.64/24')


def test_the_pair_can_still_be_typed_as_arguments():
    args = parse_args([NODE1_MAC, '10.103.1.64/24', '--vrf=MGMT'])
    set_if_ip = SetInterfaceIpByMacCommand.from_args(None, args)

    assert [(str(row.target), str(row.ip)) for row in set_if_ip._input] == [
        (NODE1_MAC.lower(), '10.103.1.64/24')]


def test_typed_arguments_leave_stdin_alone():
    "So the confirmation can still ask, as it always could"
    args = parse_args([NODE1_MAC, '10.103.1.64/24'])
    set_if_ip = SetInterfaceIpByMacCommand.from_args(None, args)

    assert not set_if_ip._stdin_is_input


def test_a_dash_per_argument_takes_stdin(monkeypatch):
    monkeypatch.setattr(sys, 'stdin', io.StringIO(TWO_LINES))
    args = parse_args([STDIN_ARG, STDIN_ARG, '--vrf=MGMT'])
    set_if_ip = SetInterfaceIpByMacCommand.from_args(None, args)

    assert set_if_ip._stdin_is_input
