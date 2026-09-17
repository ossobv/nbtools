from nbtools.lintcmd.iface_vlans import InterfaceVlansCommand

from ..nbstub import FakeNetbox


TAG = 'closso_roth'


def a_netbox():
    nb = FakeNetbox()
    nb.leaf1 = nb.add_device('leaf1')
    nb.v100 = nb.add_vlan(100)
    nb.v200 = nb.add_vlan(200)
    return nb


def test_tagged_with_tagged_vlans_is_fine():
    nb = a_netbox()
    nb.add_interface(
        nb.leaf1, 'swp1', tags=[TAG], mode='tagged',
        tagged_vlans=[nb.v100, nb.v200])

    assert InterfaceVlansCommand(nb).find() == []


def test_access_with_one_untagged_vlan_is_fine():
    nb = a_netbox()
    nb.add_interface(
        nb.leaf1, 'swp1', tags=[TAG], mode='access', untagged_vlan=nb.v100)

    assert InterfaceVlansCommand(nb).find() == []


def test_no_mode_at_all_is_reported():
    nb = a_netbox()
    nb.add_interface(nb.leaf1, 'swp1', tags=[TAG])

    assert [str(finding) for finding in InterfaceVlansCommand(nb).find()] == [
        "leaf1:swp1 #500 tag 'closso_roth': mode <none>, "
        'wanted access or tagged']


def test_tagged_all_is_reported():
    "It does not say which VLANs the port carries, which is the point"
    nb = a_netbox()
    nb.add_interface(nb.leaf1, 'swp1', tags=[TAG], mode='tagged-all')

    assert [finding.note for finding in InterfaceVlansCommand(nb).find()] == [
        "tag 'closso_roth': mode tagged-all, wanted access or tagged"]


def test_tagged_with_no_tagged_vlans_is_reported():
    nb = a_netbox()
    nb.add_interface(nb.leaf1, 'swp1', tags=[TAG], mode='tagged')

    assert [finding.note for finding in InterfaceVlansCommand(nb).find()] == [
        "tag 'closso_roth': mode tagged but no tagged vlans"]


def test_access_with_no_untagged_vlan_is_reported():
    nb = a_netbox()
    nb.add_interface(nb.leaf1, 'swp1', tags=[TAG], mode='access')

    assert [finding.note for finding in InterfaceVlansCommand(nb).find()] == [
        "tag 'closso_roth': mode access but no untagged vlan"]


def test_access_carrying_tagged_vlans_too_is_reported():
    "An access port with tagged VLANs contradicts its own mode"
    nb = a_netbox()
    nb.add_interface(
        nb.leaf1, 'swp1', tags=[TAG], mode='access',
        untagged_vlan=nb.v100, tagged_vlans=[nb.v200])

    assert [finding.note for finding in InterfaceVlansCommand(nb).find()] == [
        "tag 'closso_roth': mode access but also 1 tagged vlans"]


def test_an_untagged_interface_is_not_checked():
    nb = a_netbox()
    nb.add_interface(nb.leaf1, 'swp1')

    assert InterfaceVlansCommand(nb).find() == []


def test_the_tag_can_be_something_else():
    nb = a_netbox()
    nb.add_interface(nb.leaf1, 'swp1', tags=['vlan-port'])

    cmd = InterfaceVlansCommand(nb)
    cmd.set_tag('vlan-port')

    assert [finding.porcelain() for finding in cmd.find()] == ['leaf1:swp1']


def test_command_reports_and_counts(capsys):
    nb = a_netbox()
    nb.add_interface(nb.leaf1, 'swp1', tags=[TAG], mode='tagged')

    assert InterfaceVlansCommand(nb).run() == 1
    assert capsys.readouterr().out == (
        '---------------\n'
        'interface-vlans\n'
        '---------------\n'
        "- leaf1:swp1 #500 tag 'closso_roth': "
        'mode tagged but no tagged vlans\n')


def test_a_clean_netbox_is_silent(capsys):
    assert InterfaceVlansCommand(FakeNetbox()).run() == 0
    assert capsys.readouterr().out == ''
