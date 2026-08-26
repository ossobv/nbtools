from nbtools.lintcmd.parent_if_vrfs import ParentInterfaceVrfsCommand

from ..nbstub import FakeNetbox


def a_netbox(parent_vrf=True):
    "swp1 carrying two VRFs on subinterfaces, and a VRF of its own"
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    blue = nb.add_vrf('vrf-blue')
    main = nb.add_vrf('vrf-main')
    leaf1 = nb.add_device('leaf1')

    swp1 = nb.add_interface(
        leaf1, 'swp1', vrf=(main if parent_vrf else None))
    nb.add_interface(leaf1, 'swp1.100', parent=swp1, vrf=red)
    nb.add_interface(leaf1, 'swp1.200', parent=swp1, vrf=blue)

    return nb


def test_a_parent_in_a_vrf_over_several_vrf_children_is_reported():
    findings = ParentInterfaceVrfsCommand(a_netbox()).find()

    assert [str(finding) for finding in findings] == [
        "leaf1:swp1 #500 vrf 'vrf-main' but subinterfaces in 2 vrfs "
        '(vrf-blue, vrf-red)']


def test_a_parent_with_no_vrf_of_its_own_is_fine():
    assert ParentInterfaceVrfsCommand(a_netbox(parent_vrf=False)).find() == []


def test_one_vrf_child_does_not_make_the_parents_vrf_wrong():
    "A port and its single subinterface in one VRF is a plain layout"
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    leaf1 = nb.add_device('leaf1')
    swp1 = nb.add_interface(leaf1, 'swp1', vrf=red)
    nb.add_interface(leaf1, 'swp1.100', parent=swp1, vrf=red)

    assert ParentInterfaceVrfsCommand(nb).find() == []


def test_children_without_a_vrf_do_not_count():
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    main = nb.add_vrf('vrf-main')
    leaf1 = nb.add_device('leaf1')
    swp1 = nb.add_interface(leaf1, 'swp1', vrf=main)
    nb.add_interface(leaf1, 'swp1.100', parent=swp1, vrf=red)
    nb.add_interface(leaf1, 'swp1.200', parent=swp1)
    nb.add_interface(leaf1, 'swp1.300', parent=swp1)

    assert ParentInterfaceVrfsCommand(nb).find() == []


def test_a_missing_parent_id_does_not_hide_the_finding():
    "Going by the name reports the broken record instead of skipping it"
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    blue = nb.add_vrf('vrf-blue')
    main = nb.add_vrf('vrf-main')
    leaf1 = nb.add_device('leaf1')
    nb.add_interface(leaf1, 'swp1', vrf=main)
    nb.add_interface(leaf1, 'swp1.100', vrf=red)
    nb.add_interface(leaf1, 'swp1.200', vrf=blue)

    assert len(ParentInterfaceVrfsCommand(nb).find()) == 1


def test_the_same_port_name_on_another_device_is_another_port():
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    blue = nb.add_vrf('vrf-blue')
    main = nb.add_vrf('vrf-main')
    leaf1 = nb.add_device('leaf1')
    leaf2 = nb.add_device('leaf2')

    nb.add_interface(leaf1, 'swp1', vrf=main)
    nb.add_interface(leaf1, 'swp1.100', vrf=red)
    nb.add_interface(leaf2, 'swp1.200', vrf=blue)

    assert ParentInterfaceVrfsCommand(nb).find() == []


def test_the_same_vrf_twice_still_counts_as_two_children():
    "Two subinterfaces is what makes the port's own VRF a lie, not two VRFs"
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    leaf1 = nb.add_device('leaf1')
    swp1 = nb.add_interface(leaf1, 'swp1', vrf=red)
    nb.add_interface(leaf1, 'swp1.100', parent=swp1, vrf=red)
    nb.add_interface(leaf1, 'swp1.200', parent=swp1, vrf=red)

    assert [str(finding) for finding in
            ParentInterfaceVrfsCommand(nb).find()] == [
        "leaf1:swp1 #500 vrf 'vrf-red' but subinterfaces in 2 vrfs "
        '(vrf-red, vrf-red)']


def test_command_reports_and_counts(capsys):
    assert ParentInterfaceVrfsCommand(a_netbox()).run() == 1
    assert capsys.readouterr().out == (
        '---------------------\n'
        'parent-interface-vrfs\n'
        '---------------------\n'
        "- leaf1:swp1 #500 vrf 'vrf-main' but subinterfaces in 2 vrfs "
        '(vrf-blue, vrf-red)\n')


def test_a_clean_netbox_is_silent(capsys):
    assert ParentInterfaceVrfsCommand(FakeNetbox()).run() == 0
    assert capsys.readouterr().out == ''
