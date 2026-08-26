from nbtools.lintcmd.subif_parents import SubinterfaceParentsCommand

from ..nbstub import FakeNetbox


def a_netbox():
    """
    swp3 with four subinterfaces: one right and the three ways wrong.

    .1234 points at swp3 as it should. .1235 points at nothing, .1236
    points at swp9, and .1237 names a parent -- swp4 -- that does not
    exist on the device at all.
    """
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    swp3 = nb.add_interface(leaf1, 'swp3')
    swp9 = nb.add_interface(leaf1, 'swp9')

    nb.add_interface(leaf1, 'swp3.1234', parent=swp3)
    nb.add_interface(leaf1, 'swp3.1235')
    nb.add_interface(leaf1, 'swp3.1236', parent=swp9)
    nb.add_interface(leaf1, 'swp4.1237', parent=swp9)

    return nb


def test_a_subinterface_pointing_at_the_obvious_parent_is_fine():
    findings = SubinterfaceParentsCommand(a_netbox()).find()

    assert 'leaf1:swp3.1234' not in [
        finding.porcelain() for finding in findings]


def test_no_parent_set_is_reported_with_the_one_it_should_be():
    findings = SubinterfaceParentsCommand(a_netbox()).find()

    assert str(findings[0]) == (
        "leaf1:swp3.1235 #503 no parent set, should be 'swp3' #500")


def test_a_parent_pointing_elsewhere_is_reported_with_both():
    findings = SubinterfaceParentsCommand(a_netbox()).find()

    assert str(findings[1]) == (
        "leaf1:swp3.1236 #504 parent 'swp9' #501, should be 'swp3' #500")


def test_a_name_implying_a_parent_that_does_not_exist_is_reported():
    findings = SubinterfaceParentsCommand(a_netbox()).find()

    assert str(findings[2]) == (
        "leaf1:swp4.1237 #505 parent 'swp9' #501 but no interface "
        "named 'swp4' on this device")


def test_a_subinterface_of_nothing_with_no_parent_either():
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    nb.add_interface(leaf1, 'swp4.1237')

    assert [str(finding) for finding in
            SubinterfaceParentsCommand(nb).find()] == [
        "leaf1:swp4.1237 #500 no interface named 'swp4' on this device"]


def test_a_plain_interface_is_not_checked():
    "swp3 with no parent is a port, not a subinterface of anything"
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    nb.add_interface(leaf1, 'swp3')

    assert SubinterfaceParentsCommand(nb).find() == []


def test_a_non_numeric_suffix_is_not_a_subinterface():
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    nb.add_interface(leaf1, 'swp3')
    nb.add_interface(leaf1, 'swp3.mgmt')

    assert SubinterfaceParentsCommand(nb).find() == []


def test_a_parent_on_another_device_is_caught_by_the_id():
    "The names match, so only comparing ids reports this one"
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    leaf2 = nb.add_device('leaf2')
    nb.add_interface(leaf1, 'swp3')
    elsewhere = nb.add_interface(leaf2, 'swp3')
    nb.add_interface(leaf1, 'swp3.1234', parent=elsewhere)

    assert [str(finding) for finding in
            SubinterfaceParentsCommand(nb).find()] == [
        "leaf1:swp3.1234 #502 parent 'swp3' #501, should be 'swp3' #500"]


def test_the_obvious_parent_is_looked_for_on_the_same_device():
    "leaf2 having a swp3 does not give leaf1's swp3.1234 a parent"
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    leaf2 = nb.add_device('leaf2')
    nb.add_interface(leaf2, 'swp3')
    nb.add_interface(leaf1, 'swp3.1234')

    assert [finding.note for finding in
            SubinterfaceParentsCommand(nb).find()] == [
        "no interface named 'swp3' on this device"]


def test_a_nested_subinterface_wants_its_dotted_parent():
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    swp3 = nb.add_interface(leaf1, 'swp3')
    swp3_2 = nb.add_interface(leaf1, 'swp3.2', parent=swp3)
    nb.add_interface(leaf1, 'swp3.2.3', parent=swp3)

    assert [finding.note for finding in
            SubinterfaceParentsCommand(nb).find()] == [
        f"parent 'swp3' #{swp3.id}, should be 'swp3.2' #{swp3_2.id}"]


def test_the_finding_quotes_a_device_name_with_spaces():
    nb = FakeNetbox()
    spaced = nb.add_device('FREE (was-planned: node3.example.com)')
    nb.add_interface(spaced, 'swp3')
    nb.add_interface(spaced, 'swp3.7')

    assert [finding.porcelain() for finding in
            SubinterfaceParentsCommand(nb).find()] == [
        "'FREE (was-planned: node3.example.com)':swp3.7"]


def test_command_reports_and_counts(capsys):
    assert SubinterfaceParentsCommand(a_netbox()).run() == 3
    assert capsys.readouterr().out == (
        '--------------------\n'
        'subinterface-parents\n'
        '--------------------\n'
        "- leaf1:swp3.1235 #503 no parent set, should be 'swp3' #500\n"
        "- leaf1:swp3.1236 #504 parent 'swp9' #501, "
        "should be 'swp3' #500\n"
        "- leaf1:swp4.1237 #505 parent 'swp9' #501 but no interface "
        "named 'swp4' on this device\n")


def test_command_porcelain_prints_dev_iface_pairs(capsys):
    cmd = SubinterfaceParentsCommand(a_netbox())
    cmd.set_porcelain()

    assert cmd.run() == 3
    assert capsys.readouterr().out == (
        'leaf1:swp3.1235\n'
        'leaf1:swp3.1236\n'
        'leaf1:swp4.1237\n')


def test_a_clean_netbox_is_silent(capsys):
    assert SubinterfaceParentsCommand(FakeNetbox()).run() == 0
    assert capsys.readouterr().out == ''
