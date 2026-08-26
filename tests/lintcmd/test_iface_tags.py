from nbtools.lintcmd.iface_tags import InterfaceTagsCommand

from ..nbstub import FakeNetbox


def a_netbox():
    """
    One corelink tagged on both ends, one tagged on one end only.

    leaf1:swp1 -- leaf2:swp1 is how it should look. leaf1:swp2 says
    corelink and leaf2:swp2 does not, so one of the two is wrong and
    nothing in NetBox says which.
    """
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    leaf2 = nb.add_device('leaf2')

    nb.add_cable(
        nb.add_interface(leaf1, 'swp1', tags=['corelink']),
        nb.add_interface(leaf2, 'swp1', tags=['corelink']))
    nb.add_cable(
        nb.add_interface(leaf1, 'swp2', tags=['corelink']),
        nb.add_interface(leaf2, 'swp2'))

    return nb


def test_a_tag_on_both_ends_is_fine():
    findings = InterfaceTagsCommand(a_netbox()).find()

    assert 'leaf1:swp1' not in [finding.porcelain() for finding in findings]


def test_a_tag_on_one_end_only_is_reported_with_the_far_end():
    findings = InterfaceTagsCommand(a_netbox()).find()

    assert [str(finding) for finding in findings] == [
        "leaf1:swp2 #502 tag 'corelink' not on the far end: "
        'leaf2:swp2 #503']


def test_an_interface_with_no_cable_is_left_alone():
    "The tag says something about a link, and there is no link"
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    nb.add_interface(leaf1, 'swp1', tags=['corelink'])

    assert InterfaceTagsCommand(nb).find() == []


def test_each_of_the_default_tags_is_checked():
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    leaf2 = nb.add_device('leaf2')
    nb.add_cable(
        nb.add_interface(leaf1, 'swp1', tags=['ebgp', 'fec-off']),
        nb.add_interface(leaf2, 'swp1'))

    assert [finding.note for finding in InterfaceTagsCommand(nb).find()] == [
        "tag 'ebgp' not on the far end: leaf2:swp1 #501",
        "tag 'fec-off' not on the far end: leaf2:swp1 #501"]


def test_an_untagged_far_end_is_only_reported_for_the_tag_it_lacks():
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    leaf2 = nb.add_device('leaf2')
    nb.add_cable(
        nb.add_interface(leaf1, 'swp1', tags=['ebgp', 'fec-off']),
        nb.add_interface(leaf2, 'swp1', tags=['ebgp']))

    assert [finding.note for finding in InterfaceTagsCommand(nb).find()] == [
        "tag 'fec-off' not on the far end: leaf2:swp1 #501"]


def test_other_tags_are_not_this_commands_business():
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    leaf2 = nb.add_device('leaf2')
    nb.add_cable(
        nb.add_interface(leaf1, 'swp1', tags=['closso_roth']),
        nb.add_interface(leaf2, 'swp1'))

    assert InterfaceTagsCommand(nb).find() == []


def test_the_tag_list_can_be_replaced():
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    leaf2 = nb.add_device('leaf2')
    nb.add_cable(
        nb.add_interface(leaf1, 'swp1', tags=['closso_roth']),
        nb.add_interface(leaf2, 'swp1'))

    cmd = InterfaceTagsCommand(nb)
    cmd.set_tags(['closso_roth'])

    assert [finding.porcelain() for finding in cmd.find()] == ['leaf1:swp1']


def test_a_cable_that_lands_on_neither_end_is_not_this_finding():
    "unattached-cables reports that one"
    nb = FakeNetbox()
    leaf1 = nb.add_device('leaf1')
    nb.add_cable(nb.add_interface(leaf1, 'swp1', tags=['corelink']))

    assert InterfaceTagsCommand(nb).find() == []


def test_command_reports_and_counts(capsys):
    assert InterfaceTagsCommand(a_netbox()).run() == 1
    assert capsys.readouterr().out == (
        '-----------------------\n'
        'unpaired-interface-tags\n'
        '-----------------------\n'
        "- leaf1:swp2 #502 tag 'corelink' not on the far end: "
        'leaf2:swp2 #503\n')


def test_a_clean_netbox_is_silent(capsys):
    assert InterfaceTagsCommand(FakeNetbox()).run() == 0
    assert capsys.readouterr().out == ''
