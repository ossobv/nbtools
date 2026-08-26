from nbtools.lintcmd.dup_vrfs import (
    DuplicateIpsCommand, DuplicatePrefixesCommand)

from ..nbstub import FakeNetbox


def a_netbox_with_prefixes():
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    blue = nb.add_vrf('vrf-blue')

    nb.add_prefix('10.1.2.0/24', vrf=red)
    nb.add_prefix('10.1.2.0/24', vrf=blue)
    nb.add_prefix('10.1.3.0/24', vrf=red)

    return nb


def test_a_prefix_in_two_vrfs_is_reported():
    findings = DuplicatePrefixesCommand(a_netbox_with_prefixes()).find()

    assert [str(finding) for finding in findings] == [
        '10.1.2.0/24 x2: #200 vrf-red, #201 vrf-blue']


def test_a_prefix_in_one_vrf_is_not():
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    nb.add_prefix('10.1.3.0/24', vrf=red)

    assert DuplicatePrefixesCommand(nb).find() == []


def test_the_global_table_counts_as_a_vrf_of_its_own():
    "A prefix both inside a VRF and outside one is the same leak"
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    nb.add_prefix('10.1.2.0/24', vrf=red)
    nb.add_prefix('10.1.2.0/24')

    assert [str(finding) for finding in
            DuplicatePrefixesCommand(nb).find()] == [
        '10.1.2.0/24 x2: #200 vrf-red, #201 global']


def test_prefixes_are_matched_by_network_not_by_string():
    "NetBox stores what it was given; 10.1.2.1/24 is 10.1.2.0/24"
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    blue = nb.add_vrf('vrf-blue')
    nb.add_prefix('10.1.2.0/24', vrf=red)
    nb.add_prefix('10.1.2.1/24', vrf=blue)

    assert len(DuplicatePrefixesCommand(nb).find()) == 1


def test_the_same_prefix_twice_in_one_vrf_is_not_this_finding():
    "It is a duplicate record, but not a VRF that leaks"
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    nb.add_prefix('10.1.2.0/24', vrf=red)
    nb.add_prefix('10.1.2.0/24', vrf=red)

    assert DuplicatePrefixesCommand(nb).find() == []


def test_an_address_in_two_vrfs_is_reported():
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    blue = nb.add_vrf('vrf-blue')
    nb.add_ip('10.1.2.7/24', vrf=red)
    nb.add_ip('10.1.2.7/24', vrf=blue)

    assert [str(finding) for finding in DuplicateIpsCommand(nb).find()] == [
        '10.1.2.7 x2: #900 vrf-red, #901 vrf-blue']


def test_addresses_are_matched_without_their_mask():
    "The differing mask is a second problem, not an excuse"
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    blue = nb.add_vrf('vrf-blue')
    nb.add_ip('10.1.2.7/24', vrf=red)
    nb.add_ip('10.1.2.7/31', vrf=blue)

    assert [finding.porcelain() for finding in
            DuplicateIpsCommand(nb).find()] == ['10.1.2.7']


def test_an_anycast_pair_inside_one_vrf_is_not_reported():
    "clone-interface creates those on purpose"
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    leaf1 = nb.add_device('leaf1')
    leaf2 = nb.add_device('leaf2')
    nb.add_ip('10.1.2.1/24', iface=nb.add_interface(leaf1, 'swp1'), vrf=red)
    nb.add_ip('10.1.2.1/24', iface=nb.add_interface(leaf2, 'swp1'), vrf=red)

    assert DuplicateIpsCommand(nb).find() == []


def test_findings_come_out_in_reading_order():
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    blue = nb.add_vrf('vrf-blue')
    for vrf in (red, blue):
        nb.add_ip('2001:db8::7/64', vrf=vrf)
        nb.add_ip('10.2.0.7/24', vrf=vrf)
        nb.add_ip('10.1.0.7/24', vrf=vrf)

    assert [finding.porcelain() for finding in
            DuplicateIpsCommand(nb).find()] == [
        '10.1.0.7', '10.2.0.7', '2001:db8::7']


def test_prefix_command_reports_and_counts(capsys):
    nb = a_netbox_with_prefixes()

    assert DuplicatePrefixesCommand(nb).run() == 1
    assert capsys.readouterr().out == (
        '------------------\n'
        'duplicate-prefixes\n'
        '------------------\n'
        '- 10.1.2.0/24 x2: #200 vrf-red, #201 vrf-blue\n')


def test_prefix_command_porcelain_prints_bare_prefixes(capsys):
    nb = a_netbox_with_prefixes()
    cmd = DuplicatePrefixesCommand(nb)
    cmd.set_porcelain()

    assert cmd.run() == 1
    assert capsys.readouterr().out == '10.1.2.0/24\n'


def test_a_clean_netbox_is_silent(capsys):
    assert DuplicateIpsCommand(FakeNetbox()).run() == 0
    assert capsys.readouterr().out == ''
