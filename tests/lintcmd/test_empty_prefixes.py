from argparse import ArgumentParser

from nbtools.lintcmd.empty_prefixes import EmptyPrefixesCommand

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

    assert [finding.porcelain() for finding in findings] == [
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

    assert [finding.porcelain() for finding in cmd.find()] == ['10.1.3.0/24']


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

    assert [finding.porcelain() for finding in cmd.find()] == [
        '10.1.3.0/24', '192.168.0.0/16']


def test_status_all_reports_every_status():
    nb = FakeNetbox()
    nb.add_prefix('10.1.3.0/24', status='reserved')
    nb.add_prefix('10.1.4.0/24')

    cmd = EmptyPrefixesCommand(nb)
    cmd.set_statuses(['all'])

    assert [finding.porcelain() for finding in cmd.find()] == [
        '10.1.3.0/24', '10.1.4.0/24']


def test_no_status_leaves_the_default_in_place():
    "Both spellings of asking for nothing"
    nb = FakeNetbox()
    nb.add_prefix('10.1.3.0/24', status='reserved')
    nb.add_prefix('10.1.4.0/24')

    for statuses in (None, []):
        cmd = EmptyPrefixesCommand(nb)
        cmd.set_statuses(statuses)

        assert [finding.porcelain() for finding in cmd.find()] == [
            '10.1.4.0/24']


def test_an_empty_container_is_still_a_finding():
    "It is meant to hold prefixes, and it holds neither those nor addresses"
    nb = FakeNetbox()
    nb.add_prefix('10.0.0.0/8', status='container')

    assert [finding.porcelain() for finding in
            EmptyPrefixesCommand(nb).find()] == ['10.0.0.0/8']


def test_findings_come_out_in_reading_order():
    "v4 before v6, and by network inside a family, not by id"
    nb = FakeNetbox()
    nb.add_prefix('2001:db8::/64')
    nb.add_prefix('10.2.0.0/24')
    nb.add_prefix('10.1.0.0/24')

    assert [finding.porcelain() for finding in
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


# -- the --role flag --

def parse_roles(*argv):
    "The role words this command line asks for, flattened"
    parser = ArgumentParser(prog='empty-prefixes')
    EmptyPrefixesCommand.add_arguments(parser)

    return [word for value in (parser.parse_args(argv).role or ())
            for word in value]


def a_role_netbox():
    "One prefix per kind of role, none of them holding anything"
    nb = FakeNetbox()
    nb.add_prefix('10.1.1.0/24')
    nb.add_prefix('10.1.2.0/24', role='3rd-party')
    nb.add_prefix('10.1.3.0/24', role='mgmt')
    nb.add_prefix('10.1.4.0/24', role='customer')

    return nb


def roles_reported(roles):
    cmd = EmptyPrefixesCommand(a_role_netbox())
    cmd.set_roles(roles)

    return [finding.porcelain() for finding in cmd.find()]


def test_a_3rd_party_prefix_is_skipped_without_being_asked():
    assert [finding.porcelain() for finding in
            EmptyPrefixesCommand(a_role_netbox()).find()] == [
        '10.1.1.0/24', '10.1.3.0/24', '10.1.4.0/24']


def test_no_role_leaves_the_default_in_place():
    for roles in (None, []):
        assert roles_reported(roles) == [
            '10.1.1.0/24', '10.1.3.0/24', '10.1.4.0/24']


def test_role_reports_only_the_roles_named():
    "A prefix without a role is not included unless '' is named"
    assert roles_reported(['mgmt', '3rd-party']) == [
        '10.1.2.0/24', '10.1.3.0/24']


def test_the_empty_role_reports_only_the_prefixes_without_one():
    assert roles_reported(['']) == ['10.1.1.0/24']


def test_the_empty_role_includes_alongside_named_roles():
    assert roles_reported(['', 'mgmt']) == ['10.1.1.0/24', '10.1.3.0/24']


def test_a_bare_bang_leaves_the_prefixes_without_a_role_out():
    assert roles_reported(['!']) == [
        '10.1.2.0/24', '10.1.3.0/24', '10.1.4.0/24']


def test_a_bang_role_leaves_that_one_out_and_replaces_the_default():
    assert roles_reported(['!mgmt']) == [
        '10.1.1.0/24', '10.1.2.0/24', '10.1.4.0/24']


def test_several_bang_roles_are_left_out_together():
    assert roles_reported(['!mgmt', '!3rd-party']) == [
        '10.1.1.0/24', '10.1.4.0/24']


def test_role_all_reports_every_role():
    assert roles_reported(['all']) == [
        '10.1.1.0/24', '10.1.2.0/24', '10.1.3.0/24', '10.1.4.0/24']


def test_roles_and_statuses_both_apply():
    nb = a_role_netbox()
    nb.add_prefix('10.1.5.0/24', role='mgmt', status='reserved')

    cmd = EmptyPrefixesCommand(nb)
    cmd.set_roles(['mgmt'])

    assert [finding.porcelain() for finding in cmd.find()] == [
        '10.1.3.0/24']


def test_the_role_flag_is_repeatable_and_comma_separated():
    assert parse_roles('--role=mgmt, !3rd-party', '--role', 'all') == [
        'mgmt', '!3rd-party', 'all']


def test_no_role_flag_is_an_empty_list():
    assert parse_roles() == []


def test_the_empty_role_passes_the_flag():
    assert parse_roles('--role=', '--role=!', '--role=mgmt, ') == [
        '', '!', 'mgmt', '']


def test_from_args_carries_the_empty_role_through():
    parser = ArgumentParser(prog='empty-prefixes')
    EmptyPrefixesCommand.add_arguments(parser)
    args = parser.parse_args(['--role=!', '--role=!3rd-party'])

    cmd = EmptyPrefixesCommand.from_args(a_role_netbox(), args)

    assert [finding.porcelain() for finding in cmd.find()] == [
        '10.1.3.0/24', '10.1.4.0/24']


def test_from_args_carries_the_roles_through():
    parser = ArgumentParser(prog='empty-prefixes')
    EmptyPrefixesCommand.add_arguments(parser)
    args = parser.parse_args(['--role=!customer'])

    cmd = EmptyPrefixesCommand.from_args(a_role_netbox(), args)

    assert [finding.porcelain() for finding in cmd.find()] == [
        '10.1.1.0/24', '10.1.2.0/24', '10.1.3.0/24']
