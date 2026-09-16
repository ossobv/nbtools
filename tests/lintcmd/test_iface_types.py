import pytest

from nbtools.exceptions import StartupError
from nbtools.lintcmd.iface_types import InterfaceTypesCommand

from ..nbstub import FakeNetbox


def a_netbox():
    nb = FakeNetbox()
    pve1 = nb.add_device('pve1.example.com')

    nb.add_interface(pve1, 'vmbr0', type_='bridge')
    nb.add_interface(pve1, 'vmbr1', type_='1000base-t')
    nb.add_interface(pve1, 'vmbr1.20', type_='virtual')
    nb.add_interface(pve1, 'eno1', type_='1000base-t')

    return nb


def test_a_vmbr_that_is_not_a_bridge_is_found():
    findings = InterfaceTypesCommand(a_netbox()).find()

    assert [str(finding) for finding in findings] == [
        'pve1.example.com:vmbr1 #501 is type=1000base-t, wanted '
        'type=bridge']


def test_the_porcelain_is_the_dev_iface_nbsync_takes():
    findings = InterfaceTypesCommand(a_netbox()).find()

    assert [finding.porcelain() for finding in findings] == [
        'pve1.example.com:vmbr1']


def test_a_vlan_interface_on_a_bridge_is_left_alone():
    "vmbr1.20 is not itself a bridge, whatever type it has"
    nb = FakeNetbox()
    pve1 = nb.add_device('pve1.example.com')
    nb.add_interface(pve1, 'vmbr1.20', type_='virtual')
    nb.add_interface(pve1, 'vmbr1.30', type_='1000base-t')

    assert InterfaceTypesCommand(nb).find() == []


def test_the_prefix_is_matched_with_case():
    "name__isw ignores case; a VMBR0 is not a Proxmox bridge"
    nb = FakeNetbox()
    nb.add_interface(nb.add_device('sw1'), 'VMBR0', type_='1000base-t')

    assert InterfaceTypesCommand(nb).find() == []


def test_limit_bridge_keeps_the_bridges():
    cmd = InterfaceTypesCommand(a_netbox())
    cmd.set_limit('bridge')

    assert [finding.porcelain() for finding in cmd.find()] == [
        'pve1.example.com:vmbr1']


def test_porcelain_without_a_limit_is_refused():
    with pytest.raises(StartupError, match='--limit'):
        InterfaceTypesCommand(a_netbox()).set_porcelain()


def test_porcelain_with_a_limit_prints_dev_iface(capsys):
    cmd = InterfaceTypesCommand(a_netbox())
    cmd.set_limit('bridge')
    cmd.set_porcelain()

    assert cmd.run() == 1
    assert capsys.readouterr().out == 'pve1.example.com:vmbr1\n'


def test_command_reports_and_counts(capsys):
    assert InterfaceTypesCommand(a_netbox()).run() == 1
    assert capsys.readouterr().out == (
        '---------------\n'
        'interface-types\n'
        '---------------\n'
        '- pve1.example.com:vmbr1 #501 is type=1000base-t, wanted '
        'type=bridge\n')
