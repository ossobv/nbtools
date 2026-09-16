import pytest

from nbtools.exceptions import StartupError
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


def test_the_listing_says_which_kind_and_where():
    findings = DiscoveredItemsCommand(a_netbox()).find()

    assert [str(finding) for finding in findings] == [
        'device node9.example.com #400 filed under cluster Discovery',
        'virtual-machine vm9.example.com #700 filed under cluster '
        'Discovery']


def test_a_device_in_the_discovery_site_is_listed():
    nb = FakeNetbox()
    nb.add_device('node9.example.com', site=nb.add_site('Discovery'))
    nb.add_device('node1.example.com', site=nb.add_site('ams1'))

    assert [str(finding) for finding in DiscoveredItemsCommand(
        nb).find()] == [
        'device node9.example.com #400 filed under site Discovery']


def test_a_device_by_the_discovery_manufacturer_is_listed():
    nb = FakeNetbox()
    nb.add_device(
        'node9.example.com', manufacturer=nb.add_manufacturer('Discovery'))
    nb.add_device(
        'node1.example.com', manufacturer=nb.add_manufacturer('Supermicro'))

    assert [str(finding) for finding in DiscoveredItemsCommand(
        nb).find()] == [
        'device node9.example.com #400 filed under manufacturer Discovery']


def test_a_device_filed_twice_over_is_listed_once():
    nb = FakeNetbox()
    nb.add_device(
        'node9.example.com', site=nb.add_site('Discovery'),
        manufacturer=nb.add_manufacturer('Discovery'))

    assert [str(finding) for finding in DiscoveredItemsCommand(
        nb).find()] == [
        'device node9.example.com #400 filed under site Discovery, '
        'manufacturer Discovery']


def test_the_name_is_matched_ignoring_case():
    nb = FakeNetbox()
    nb.add_device('node9.example.com', site=nb.add_site('discovery'))

    assert len(DiscoveredItemsCommand(nb).find()) == 1


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


def test_the_name_can_be_something_else():
    nb = FakeNetbox()
    cluster = nb.add_cluster('Autodetected')
    nb.add_device('node9.example.com', cluster=cluster)
    nb.add_device('node8.example.com', site=nb.add_site('Autodetected'))

    cmd = DiscoveredItemsCommand(nb)
    cmd.set_name('Autodetected')

    assert len(cmd.find()) == 2


def test_porcelain_without_a_limit_is_refused():
    with pytest.raises(StartupError, match='--limit'):
        DiscoveredItemsCommand(a_netbox()).set_porcelain()


def test_porcelain_with_a_limit_prints_names(capsys):
    cmd = DiscoveredItemsCommand(a_netbox())
    cmd.set_limit('vms')
    cmd.set_porcelain()

    assert cmd.run() == 1
    assert capsys.readouterr().out == 'vm9.example.com\n'


def test_a_netbox_with_no_discovery_cluster_is_silent(capsys):
    assert DiscoveredItemsCommand(FakeNetbox()).run() == 0
    assert capsys.readouterr().out == ''


def test_command_reports_and_counts(capsys):
    assert DiscoveredItemsCommand(a_netbox()).run() == 2
    assert capsys.readouterr().out == (
        '----------------\n'
        'discovered-items\n'
        '----------------\n'
        '- device node9.example.com #400 filed under cluster Discovery\n'
        '- virtual-machine vm9.example.com #700 filed under cluster '
        'Discovery\n')
