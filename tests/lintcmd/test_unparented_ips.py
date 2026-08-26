from nbtools.lintcmd.unparented_ips import UnparentedIpsCommand

from ..nbstub import FakeNetbox


def a_netbox():
    """
    One address in a proper /24, one with only a /16 over it, one bare.

    10.1.2.7 is fine. 10.9.0.7 sits in a /16 and nothing smaller, so
    nobody wrote its subnet down. 172.16.0.7 has nothing over it at
    all.
    """
    nb = FakeNetbox()
    nb.add_prefix('10.1.2.0/24')
    nb.add_prefix('10.9.0.0/16')

    nb.add_ip('10.1.2.7/24')
    nb.add_ip('10.9.0.7/24')
    nb.add_ip('172.16.0.7/24')

    return nb


def test_an_address_in_a_slash_24_is_fine():
    findings = UnparentedIpsCommand(a_netbox()).find()

    assert '10.1.2.7' not in [finding.value for finding in findings]


def test_an_address_with_only_a_bigger_prefix_is_reported():
    findings = UnparentedIpsCommand(a_netbox()).find()

    assert str(findings[0]) == (
        '10.9.0.7/24 #901 status=active vrf=global '
        '(covered by /16, wanted /24 or smaller)')


def test_an_address_with_no_prefix_at_all_is_reported():
    findings = UnparentedIpsCommand(a_netbox()).find()

    assert str(findings[1]) == (
        '172.16.0.7/24 #902 status=active vrf=global '
        '(no parent prefix, wanted /24 or smaller)')


def test_a_longer_prefix_than_asked_for_is_still_a_parent():
    nb = FakeNetbox()
    nb.add_prefix('10.1.2.0/28')
    nb.add_ip('10.1.2.7/24')

    assert UnparentedIpsCommand(nb).find() == []


def test_a_host_prefix_counts_as_a_parent():
    "Strange to have, and empty-prefixes will say so, but not this finding"
    nb = FakeNetbox()
    nb.add_prefix('10.1.2.7/32')
    nb.add_ip('10.1.2.7/24')

    assert UnparentedIpsCommand(nb).find() == []


def test_the_parent_has_to_be_in_the_same_vrf():
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    nb.add_prefix('10.1.2.0/24')
    nb.add_ip('10.1.2.7/24', vrf=red)

    assert [finding.porcelain() for finding in
            UnparentedIpsCommand(nb).find()] == ['10.1.2.7/24']


def test_the_recorded_mask_of_the_address_does_not_matter():
    "A /32 host record still wants a /24 above it"
    nb = FakeNetbox()
    nb.add_prefix('10.1.2.0/24')
    nb.add_ip('10.1.2.7/32')

    assert UnparentedIpsCommand(nb).find() == []


def test_ipv6_uses_the_slash_64_default():
    nb = FakeNetbox()
    nb.add_prefix('2001:db8::/48')
    nb.add_ip('2001:db8::7/64')

    assert [str(finding) for finding in UnparentedIpsCommand(nb).find()] == [
        '2001:db8::7/64 #900 status=active vrf=global '
        '(covered by /48, wanted /64 or smaller)']


def test_ipv6_in_a_slash_64_is_fine():
    nb = FakeNetbox()
    nb.add_prefix('2001:db8::/64')
    nb.add_ip('2001:db8::7/64')

    assert UnparentedIpsCommand(nb).find() == []


def test_min_prefixlen_can_be_relaxed():
    nb = FakeNetbox()
    nb.add_prefix('10.9.0.0/16')
    nb.add_ip('10.9.0.7/24')

    cmd = UnparentedIpsCommand(nb)
    cmd.set_min_prefixlen(16, 48)

    assert cmd.find() == []


def test_min_prefixlen_can_be_tightened():
    nb = FakeNetbox()
    nb.add_prefix('10.1.2.0/24')
    nb.add_ip('10.1.2.7/24')

    cmd = UnparentedIpsCommand(nb)
    cmd.set_min_prefixlen(25, 64)

    assert [str(finding) for finding in cmd.find()] == [
        '10.1.2.7/24 #900 status=active vrf=global '
        '(covered by /24, wanted /25 or smaller)']


def test_findings_come_out_in_reading_order():
    nb = FakeNetbox()
    nb.add_ip('2001:db8::7/64')
    nb.add_ip('10.2.0.7/24')
    nb.add_ip('10.1.0.7/24')

    assert [finding.value for finding in UnparentedIpsCommand(nb).find()] == [
        '10.1.0.7/24', '10.2.0.7/24', '2001:db8::7/64']


def test_command_reports_and_counts(capsys):
    assert UnparentedIpsCommand(a_netbox()).run() == 2
    assert capsys.readouterr().out.startswith(
        '--------------\n'
        'unparented-ips\n'
        '--------------\n'
        '- 10.9.0.7/24 #901 ')


def test_a_clean_netbox_is_silent(capsys):
    assert UnparentedIpsCommand(FakeNetbox()).run() == 0
    assert capsys.readouterr().out == ''
