from nbtools.lintcmd.empty_prefixes import EmptyPrefixesCommand
from nbtools.types import VrfPrefix

from ..nbstub import FakeNetbox


def a_netbox():
    """
    One container that is doing its job, and two prefixes that are not.

    10.0.0.0/8 holds a child, so it stays. 10.1.2.0/24 holds an
    address, so it stays. 10.1.3.0/24 and 2001:db8::/64 hold nothing.
    """
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    swp1 = nb.add_interface(leaf1, 'swp1')

    nb.add_prefix('10.0.0.0/8', status='container')
    nb.add_prefix('10.1.2.0/24')
    nb.add_prefix('10.1.3.0/24')
    nb.add_prefix('2001:db8::/64')
    nb.add_ip('10.1.2.7/24', iface=swp1)

    return nb


def test_only_the_prefixes_holding_nothing_are_reported():
    findings = EmptyPrefixesCommand(a_netbox()).find()

    assert [finding.value for finding in findings] == [
        '10.1.3.0/24', '2001:db8::/64']


def test_the_listing_names_the_id_the_status_and_the_vrf():
    findings = EmptyPrefixesCommand(a_netbox()).find()

    assert str(findings[0]) == '10.1.3.0/24 #202 status=active vrf=global'


def test_an_unassigned_address_still_fills_its_prefix():
    "The address is a finding of its own; the prefix is not empty"
    nb = FakeNetbox()
    nb.add_prefix('10.1.2.0/24')
    nb.add_ip('10.1.2.7/24')

    assert EmptyPrefixesCommand(nb).find() == []


def test_a_prefix_is_only_filled_from_its_own_vrf():
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    nb.add_prefix('10.1.2.0/24', vrf=red)
    nb.add_ip('10.1.2.7/24')

    findings = EmptyPrefixesCommand(nb).find()
    assert [str(finding) for finding in findings] == [
        '10.1.2.0/24 #200 status=active vrf=vrf-red']


def test_family_limits_the_report_to_one_family():
    nb = FakeNetbox()
    nb.add_prefix('10.1.3.0/24')
    nb.add_prefix('2001:db8::/64')

    cmd = EmptyPrefixesCommand(nb)
    cmd.set_family('4')

    assert [finding.value for finding in cmd.find()] == ['10.1.3.0/24']


def test_no_family_reports_both_of_them():
    nb = FakeNetbox()
    nb.add_prefix('10.1.3.0/24')
    nb.add_prefix('2001:db8::/64')

    cmd = EmptyPrefixesCommand(nb)
    cmd.set_family(None)

    assert [finding.value for finding in cmd.find()] == [
        '10.1.3.0/24', '2001:db8::/64']


def test_the_family_narrows_the_address_table_as_well():
    """
    Both reads take the family, and emptiness still comes out right.

    A prefix is only ever filled from its own family, so dropping the
    other one from the address table cannot change the answer -- and
    that table is the expensive half of the two requests.
    """
    nb = FakeNetbox()
    nb.add_prefix('2001:db8::/64')
    nb.add_prefix('2001:db8:1::/64')
    nb.add_ip('2001:db8::7/64')
    nb.add_ip('10.1.3.7/24')

    cmd = EmptyPrefixesCommand(nb)
    cmd.set_family('6')

    assert [finding.value for finding in cmd.find()] == ['2001:db8:1::/64']


def test_a_container_filled_from_the_other_family_cannot_happen():
    "Nothing v4 fills a v6 container, so the filtered read loses nothing"
    nb = FakeNetbox()
    nb.add_prefix('2001:db8::/32', status='container')
    nb.add_prefix('10.0.0.0/8')

    cmd = EmptyPrefixesCommand(nb)
    cmd.set_family('6')

    assert [finding.value for finding in cmd.find()] == ['2001:db8::/32']


def test_status_reports_only_the_kinds_named():
    "An empty container is still empty, but not everyone wants to hear it"
    nb = FakeNetbox()
    nb.add_prefix('10.0.0.0/8', status='container')
    nb.add_prefix('10.1.3.0/24')

    cmd = EmptyPrefixesCommand(nb)
    cmd.set_statuses(['active'])

    assert [finding.value for finding in cmd.find()] == ['10.1.3.0/24']


def test_a_reserved_prefix_is_skipped_without_being_asked():
    "Those are the ranges somebody else hands the addresses out of"
    nb = FakeNetbox()
    nb.add_prefix('10.1.3.0/24', status='reserved')

    assert EmptyPrefixesCommand(nb).find() == []


def test_status_can_ask_for_the_reserved_ones_on_their_own():
    "The allowlist means naming it is enough; there is nothing to un-skip"
    nb = FakeNetbox()
    nb.add_prefix('10.1.3.0/24', status='reserved')
    nb.add_prefix('10.1.4.0/24')

    cmd = EmptyPrefixesCommand(nb)
    cmd.set_statuses(['reserved'])

    assert [str(finding) for finding in cmd.find()] == [
        '10.1.3.0/24 #200 status=reserved vrf=global']


def test_several_statuses_are_reported_together():
    "The container is off on its own, so nothing inside it fills it"
    nb = FakeNetbox()
    nb.add_prefix('192.168.0.0/16', status='container')
    nb.add_prefix('10.1.3.0/24', status='reserved')
    nb.add_prefix('10.1.4.0/24')

    cmd = EmptyPrefixesCommand(nb)
    cmd.set_statuses(['container', 'reserved'])

    assert [finding.value for finding in cmd.find()] == [
        '10.1.3.0/24', '192.168.0.0/16']


def test_status_all_reports_every_status():
    nb = FakeNetbox()
    nb.add_prefix('10.1.3.0/24', status='reserved')
    nb.add_prefix('10.1.4.0/24')

    cmd = EmptyPrefixesCommand(nb)
    cmd.set_statuses(['all'])

    assert [finding.value for finding in cmd.find()] == [
        '10.1.3.0/24', '10.1.4.0/24']


def test_no_status_leaves_the_default_in_place():
    "Both spellings of asking for nothing"
    nb = FakeNetbox()
    nb.add_prefix('10.1.3.0/24', status='reserved')
    nb.add_prefix('10.1.4.0/24')

    for statuses in (None, []):
        cmd = EmptyPrefixesCommand(nb)
        cmd.set_statuses(statuses)

        assert [finding.value for finding in cmd.find()] == ['10.1.4.0/24']


def test_an_empty_container_is_still_a_finding():
    "It is meant to hold prefixes, and it holds neither those nor addresses"
    nb = FakeNetbox()
    nb.add_prefix('10.0.0.0/8', status='container')

    assert [finding.value for finding in
            EmptyPrefixesCommand(nb).find()] == ['10.0.0.0/8']


def test_findings_come_out_in_reading_order():
    "v4 before v6, and by network inside a family, not by id"
    nb = FakeNetbox()
    nb.add_prefix('2001:db8::/64')
    nb.add_prefix('10.2.0.0/24')
    nb.add_prefix('10.1.0.0/24')

    assert [finding.value for finding in
            EmptyPrefixesCommand(nb).find()] == [
        '10.1.0.0/24', '10.2.0.0/24', '2001:db8::/64']


def test_a_netbox_with_nothing_empty_is_silent(capsys):
    nb = FakeNetbox()
    nb.add_prefix('10.1.2.0/24')
    nb.add_ip('10.1.2.7/24')

    assert EmptyPrefixesCommand(nb).run() == 0
    assert capsys.readouterr().out == ''


def test_command_reports_and_counts(capsys):
    assert EmptyPrefixesCommand(a_netbox()).run() == 2
    assert capsys.readouterr().out == (
        '--------------\n'
        'empty-prefixes\n'
        '--------------\n'
        '- 10.1.3.0/24 #202 status=active vrf=global\n'
        '- 2001:db8::/64 #203 status=active vrf=global\n')


# -- what --porcelain has to say for itself --

def test_porcelain_carries_the_vrf_with_the_prefix():
    "The prefix alone would not name a record for nbsync to act on"
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    nb.add_prefix('10.1.3.0/24', vrf=red)

    assert [finding.porcelain() for finding in
            EmptyPrefixesCommand(nb).find()] == ['10.1.3.0/24@vrf-red']


def test_porcelain_leaves_the_vrf_empty_for_the_global_table():
    "An empty half spells the absent one, the way DevIface.NONE does"
    nb = FakeNetbox()
    nb.add_prefix('10.1.3.0/24')

    assert [finding.porcelain() for finding in
            EmptyPrefixesCommand(nb).find()] == ['10.1.3.0/24@']


def test_porcelain_normalises_a_prefix_off_its_own_boundary():
    nb = FakeNetbox()
    nb.add_prefix('10.1.3.1/24')

    assert [finding.porcelain() for finding in
            EmptyPrefixesCommand(nb).find()] == ['10.1.3.0/24@']


def test_porcelain_output_is_what_delete_prefix_takes(capsys):
    "One token per line, so xargs hands each over as one argument"
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    nb.add_prefix('10.1.3.0/24', vrf=red)
    nb.add_prefix('10.1.4.0/24')

    cmd = EmptyPrefixesCommand(nb)
    cmd.set_porcelain()
    assert cmd.run() == 2

    lines = capsys.readouterr().out.split()
    assert lines == ['10.1.3.0/24@vrf-red', '10.1.4.0/24@']
    assert [str(VrfPrefix(line)) for line in lines] == lines
