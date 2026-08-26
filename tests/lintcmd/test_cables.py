from nbtools.lintcmd.cables import UnattachedCablesCommand

from ..nbstub import FakeNetbox


def a_netbox():
    """
    One cable plugged in at both ends, one at one end, one at neither.
    """
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    leaf2 = nb.add_device('leaf2')

    nb.add_cable(
        nb.add_interface(leaf1, 'swp1'), nb.add_interface(leaf2, 'swp1'))
    nb.add_cable(nb.add_interface(leaf1, 'swp4'))
    nb.add_cable()

    return nb


def test_a_cable_attached_at_both_ends_is_fine():
    findings = UnattachedCablesCommand(a_netbox()).find()

    assert [finding.porcelain() for finding in findings] == ['101', '102']


def test_a_cable_with_one_end_missing_names_the_end_it_has():
    findings = UnattachedCablesCommand(a_netbox()).find()

    assert str(findings[0]) == (
        'cable #101 status=connected a=leaf1:swp4 b=<none>')


def test_a_cable_attached_to_nothing_at_all_is_reported_too():
    findings = UnattachedCablesCommand(a_netbox()).find()

    assert str(findings[1]) == (
        'cable #102 status=connected a=<none> b=<none>')


def test_a_missing_a_end_is_reported_as_readily_as_a_missing_b_end():
    nb = FakeNetbox()
    leaf2 = nb.add_device('leaf2')
    nb.add_cable(b_end=nb.add_interface(leaf2, 'swp1'))

    assert [str(finding) for finding in
            UnattachedCablesCommand(nb).find()] == [
        'cable #100 status=connected a=<none> b=leaf2:swp1']


def test_the_finding_quotes_a_device_name_with_spaces():
    nb = FakeNetbox()
    spaced = nb.add_device('FREE (was-planned: node3.example.com)')
    nb.add_cable(nb.add_interface(spaced, 'swp1'))

    assert str(UnattachedCablesCommand(nb).find()[0]) == (
        "cable #100 status=connected "
        "a='FREE (was-planned: node3.example.com)':swp1 b=<none>")


def test_the_status_is_the_value_not_the_label():
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    nb.add_cable(nb.add_interface(leaf1, 'swp1'), status='planned')

    assert 'status=planned' in str(UnattachedCablesCommand(nb).find()[0])


def test_command_reports_and_counts(capsys):
    assert UnattachedCablesCommand(a_netbox()).run() == 2
    assert capsys.readouterr().out == (
        '-----------------\n'
        'unattached-cables\n'
        '-----------------\n'
        '- cable #101 status=connected a=leaf1:swp4 b=<none>\n'
        '- cable #102 status=connected a=<none> b=<none>\n')


def test_a_clean_netbox_is_silent(capsys):
    assert UnattachedCablesCommand(FakeNetbox()).run() == 0
    assert capsys.readouterr().out == ''
