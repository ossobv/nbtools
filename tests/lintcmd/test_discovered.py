from nbtools.lintcmd.discovered import DiscoveredItemsCommand

from ..nbstub import FakeNetbox


def a_netbox():
    nb = FakeNetbox()
    discovery = nb.add_cluster('Discovery')
    placed = nb.add_cluster('rack12')

    nb.add_device('node9.example.com', cluster=discovery)
    nb.add_device('node1.example.com', cluster=placed)
    nb.add_vm('vm9.example.com', cluster=discovery)
    nb.add_vm('vm1.example.com', cluster=placed)

    return nb


def test_only_the_discovery_cluster_is_listed():
    findings = DiscoveredItemsCommand(a_netbox()).find()

    assert [finding.porcelain() for finding in findings] == [
        'node9.example.com', 'vm9.example.com']


def test_the_listing_says_which_kind_and_which_cluster():
    findings = DiscoveredItemsCommand(a_netbox()).find()

    assert [str(finding) for finding in findings] == [
        'device node9.example.com #400 in cluster Discovery',
        'virtual-machine vm9.example.com #700 in cluster Discovery']


def test_limit_devices_drops_the_virtual_machines():
    cmd = DiscoveredItemsCommand(a_netbox())
    cmd.set_limit('devices')

    assert [finding.porcelain() for finding in cmd.find()] == [
        'node9.example.com']


def test_limit_vms_drops_the_devices():
    cmd = DiscoveredItemsCommand(a_netbox())
    cmd.set_limit('vms')

    assert [finding.porcelain() for finding in cmd.find()] == [
        'vm9.example.com']


def test_the_cluster_name_is_matched_as_a_substring():
    "DESIGN.md looks it up with q=, which is a freeform search"
    nb = FakeNetbox()
    cluster = nb.add_cluster('Discovery (auto)')
    nb.add_device('node9.example.com', cluster=cluster)

    assert [str(finding) for finding in
            DiscoveredItemsCommand(nb).find()] == [
        "device node9.example.com #400 in cluster 'Discovery (auto)'"]


def test_the_cluster_can_be_something_else():
    nb = FakeNetbox()
    cluster = nb.add_cluster('Autodetected')
    nb.add_device('node9.example.com', cluster=cluster)

    cmd = DiscoveredItemsCommand(nb)
    cmd.set_cluster('Autodetected')

    assert len(cmd.find()) == 1


def test_a_netbox_with_no_discovery_cluster_is_silent(capsys):
    assert DiscoveredItemsCommand(FakeNetbox()).run() == 0
    assert capsys.readouterr().out == ''


def test_command_reports_and_counts(capsys):
    assert DiscoveredItemsCommand(a_netbox()).run() == 2
    assert capsys.readouterr().out == (
        '----------------\n'
        'discovered-items\n'
        '----------------\n'
        '- device node9.example.com #400 in cluster Discovery\n'
        '- virtual-machine vm9.example.com #700 in cluster Discovery\n')
