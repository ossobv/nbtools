from nbtools.lintcmd.unassigned_ips import UnassignedIpsCommand

from ..nbstub import FakeNetbox


def a_netbox():
    """
    Two held addresses and two loose ones, in both families.

    The loose ones are what the command is for: 10.0.0.9/24 is the
    leftover of a machine that went away, and 2001:db8::9/64 is the
    same thing a family over.
    """
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    leaf1 = nb.add_device('leaf1')
    swp1 = nb.add_interface(leaf1, 'swp1')

    nb.add_ip('10.0.0.1/24', iface=swp1, vrf=red)
    nb.add_ip('10.0.0.9/24', vrf=red, status='deprecated')
    nb.add_ip('2001:db8::1/64', iface=swp1)
    nb.add_ip('2001:db8::9/64')

    return nb


def test_only_the_addresses_on_no_interface_are_reported():
    findings = UnassignedIpsCommand(a_netbox()).find()

    assert [finding.porcelain() for finding in findings] == [
        '10.0.0.9/24', '2001:db8::9/64']


def test_the_listing_names_the_id_the_status_and_the_vrf():
    findings = UnassignedIpsCommand(a_netbox()).find()

    assert str(findings[0]) == (
        '10.0.0.9/24 #901 status=deprecated vrf=vrf-red')


def test_an_address_in_no_vrf_says_global():
    "NetBox leaves the field empty; a column of names reads better"
    findings = UnassignedIpsCommand(a_netbox()).find()

    assert str(findings[1]) == (
        '2001:db8::9/64 #903 status=active vrf=global')


def test_family_limits_the_report_to_one_family():
    cmd = UnassignedIpsCommand(a_netbox())
    cmd.set_family('6')

    assert [finding.porcelain() for finding in cmd.find()] == [
        '2001:db8::9/64']


def a_netbox_of_every_status():
    "One loose address per status, so a filter shows as a subset"
    nb = FakeNetbox()
    nb.add_ip('10.0.0.1/24')
    nb.add_ip('10.0.0.2/24', status='reserved')
    nb.add_ip('10.0.0.3/24', status='deprecated')
    nb.add_ip('10.0.0.4/24', status='dhcp')
    nb.add_ip('10.0.0.5/24', status='slaac')

    return nb


def test_a_reserved_address_is_skipped_without_being_asked():
    "Held on purpose with nothing on it: sitting loose is its whole point"
    nb = FakeNetbox()
    nb.add_ip('10.0.0.2/24', status='reserved')

    assert UnassignedIpsCommand(nb).find() == []


def test_the_other_statuses_are_reported_by_default():
    "dhcp and slaac included -- a loose lease is the leftover we want"
    findings = UnassignedIpsCommand(a_netbox_of_every_status()).find()

    assert [finding.porcelain() for finding in findings] == [
        '10.0.0.1/24', '10.0.0.3/24', '10.0.0.4/24', '10.0.0.5/24']


def test_status_reports_only_the_kinds_named():
    cmd = UnassignedIpsCommand(a_netbox_of_every_status())
    cmd.set_statuses(['active', 'dhcp'])

    assert [finding.porcelain() for finding in cmd.find()] == [
        '10.0.0.1/24', '10.0.0.4/24']


def test_status_can_ask_for_the_reserved_ones_on_their_own():
    cmd = UnassignedIpsCommand(a_netbox_of_every_status())
    cmd.set_statuses(['reserved'])

    assert [str(finding) for finding in cmd.find()] == [
        '10.0.0.2/24 #901 status=reserved vrf=global']


def test_status_all_reports_every_status():
    cmd = UnassignedIpsCommand(a_netbox_of_every_status())
    cmd.set_statuses(['all'])

    assert [finding.porcelain() for finding in cmd.find()] == [
        '10.0.0.1/24', '10.0.0.2/24', '10.0.0.3/24', '10.0.0.4/24',
        '10.0.0.5/24']


def test_status_and_family_narrow_together():
    nb = a_netbox_of_every_status()
    nb.add_ip('2001:db8::4/64', status='dhcp')

    cmd = UnassignedIpsCommand(nb)
    cmd.set_family('6')
    cmd.set_statuses(['dhcp'])

    assert [finding.porcelain() for finding in cmd.find()] == [
        '2001:db8::4/64']


def test_a_netbox_where_everything_is_held_is_silent(capsys):
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    swp1 = nb.add_interface(leaf1, 'swp1')
    nb.add_ip('10.0.0.1/24', iface=swp1)

    assert UnassignedIpsCommand(nb).run() == 0
    assert capsys.readouterr().out == ''


def test_command_reports_and_counts(capsys):
    assert UnassignedIpsCommand(a_netbox()).run() == 2
    assert capsys.readouterr().out == (
        '--------------\n'
        'unassigned-ips\n'
        '--------------\n'
        '- 10.0.0.9/24 #901 status=deprecated vrf=vrf-red\n'
        '- 2001:db8::9/64 #903 status=active vrf=global\n')


def test_command_porcelain_prints_bare_addresses(capsys):
    cmd = UnassignedIpsCommand(a_netbox())
    cmd.set_porcelain()

    assert cmd.run() == 2
    assert capsys.readouterr().out == (
        '10.0.0.9/24\n'
        '2001:db8::9/64\n')
