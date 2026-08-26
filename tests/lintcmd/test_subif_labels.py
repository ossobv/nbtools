from nbtools.lintcmd.subif_labels import SubinterfaceLabelsCommand

from ..nbstub import FakeNetbox


def a_netbox():
    """
    One subinterface labelled right, and the three ways to get it wrong.

    swp1.2107 carries OSSO_BACKUP and says so. swp1.2108 says nothing,
    swp1.2109 says the wrong thing, and swp1.2110 kept a label after
    its VRF went away.
    """
    nb = FakeNetbox()
    backup = nb.add_vrf('OSSO_BACKUP')
    main = nb.add_vrf('OSSO_MAIN')
    leaf1 = nb.add_device('leaf1')
    swp1 = nb.add_interface(leaf1, 'swp1')

    nb.add_interface(
        leaf1, 'swp1.2107', parent=swp1, vrf=backup, label='OSSO_BACKUP')
    nb.add_interface(leaf1, 'swp1.2108', parent=swp1, vrf=backup)
    nb.add_interface(
        leaf1, 'swp1.2109', parent=swp1, vrf=main, label='OSSO_BACKUP')
    nb.add_interface(leaf1, 'swp1.2110', parent=swp1, label='OSSO_MAIN')

    return nb


def test_a_subinterface_labelled_with_its_vrf_is_fine():
    findings = SubinterfaceLabelsCommand(a_netbox()).find()

    assert 'leaf1:swp1.2107' not in [
        finding.porcelain() for finding in findings]


def test_an_empty_label_is_reported():
    findings = SubinterfaceLabelsCommand(a_netbox()).find()

    assert str(findings[0]) == (
        "leaf1:swp1.2108 #502 label '' should be 'OSSO_BACKUP'")


def test_a_label_naming_the_wrong_vrf_is_reported():
    findings = SubinterfaceLabelsCommand(a_netbox()).find()

    assert str(findings[1]) == (
        "leaf1:swp1.2109 #503 label 'OSSO_BACKUP' should be 'OSSO_MAIN'")


def test_a_label_left_behind_by_a_vrf_that_moved_is_reported():
    findings = SubinterfaceLabelsCommand(a_netbox()).find()

    assert str(findings[2]) == (
        "leaf1:swp1.2110 #504 label 'OSSO_MAIN' but no vrf")


def test_a_subinterface_with_neither_vrf_nor_label_is_left_alone():
    "That is a missing VRF, which is not this check's business"
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    swp1 = nb.add_interface(leaf1, 'swp1')
    nb.add_interface(leaf1, 'swp1.2107', parent=swp1)

    assert SubinterfaceLabelsCommand(nb).find() == []


def test_a_plain_interface_is_not_a_subinterface():
    "swp1 in a VRF with no label is not this finding"
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    leaf1 = nb.add_device('leaf1')
    nb.add_interface(leaf1, 'swp1', vrf=red)

    assert SubinterfaceLabelsCommand(nb).find() == []


def test_a_non_numeric_suffix_is_not_a_subinterface():
    "'swp1.mgmt' is a name that holds a dot, and carries no VRF tag"
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    leaf1 = nb.add_device('leaf1')
    swp1 = nb.add_interface(leaf1, 'swp1')
    nb.add_interface(leaf1, 'swp1.mgmt', parent=swp1, vrf=red)

    assert SubinterfaceLabelsCommand(nb).find() == []


def test_the_finding_quotes_a_device_name_with_spaces():
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    spaced = nb.add_device('FREE (was-planned: node3.example.com)')
    swp1 = nb.add_interface(spaced, 'swp1')
    nb.add_interface(spaced, 'swp1.7', parent=swp1, vrf=red)

    assert [finding.porcelain() for finding in
            SubinterfaceLabelsCommand(nb).find()] == [
        "'FREE (was-planned: node3.example.com)':swp1.7"]


def test_command_reports_and_counts(capsys):
    assert SubinterfaceLabelsCommand(a_netbox()).run() == 3
    assert capsys.readouterr().out == (
        '-------------------\n'
        'subinterface-labels\n'
        '-------------------\n'
        "- leaf1:swp1.2108 #502 label '' should be 'OSSO_BACKUP'\n"
        "- leaf1:swp1.2109 #503 label 'OSSO_BACKUP' should be 'OSSO_MAIN'\n"
        "- leaf1:swp1.2110 #504 label 'OSSO_MAIN' but no vrf\n")


def test_command_porcelain_prints_dev_iface_pairs(capsys):
    "Which is the argument every nbsync interface command takes"
    cmd = SubinterfaceLabelsCommand(a_netbox())
    cmd.set_porcelain()

    assert cmd.run() == 3
    assert capsys.readouterr().out == (
        'leaf1:swp1.2108\n'
        'leaf1:swp1.2109\n'
        'leaf1:swp1.2110\n')


def test_a_clean_netbox_is_silent(capsys):
    assert SubinterfaceLabelsCommand(FakeNetbox()).run() == 0
    assert capsys.readouterr().out == ''
