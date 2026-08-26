from nbtools.lintcmd.bmc_macs import BmcMacsCommand

from ..nbstub import FakeNetbox


def a_netbox():
    """
    Three BMCs: one right, one with none, one with two.

    node1 is how it should look. node2's BMC cannot be found at all,
    and nothing can tell which of node3's two MACs to use.
    """
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    node2 = nb.add_device('node2.example.com')
    node3 = nb.add_device('node3.example.com')

    nb.add_mac('AA:BB:CC:00:00:01', iface=nb.add_interface(node1, 'BMC'))
    nb.add_interface(node2, 'BMC')
    bmc3 = nb.add_interface(node3, 'BMC')
    nb.add_mac('AA:BB:CC:00:00:03', iface=bmc3)
    nb.add_mac('AA:BB:CC:00:00:04', iface=bmc3)

    return nb


def test_a_bmc_with_exactly_one_mac_is_fine():
    findings = BmcMacsCommand(a_netbox()).find()

    assert 'node1.example.com:BMC' not in [
        finding.porcelain() for finding in findings]


def test_a_bmc_with_no_mac_is_reported():
    findings = BmcMacsCommand(a_netbox()).find()

    assert str(findings[0]) == 'node2.example.com:BMC #501 no mac address'


def test_a_bmc_with_two_macs_is_reported_with_both():
    findings = BmcMacsCommand(a_netbox()).find()

    assert str(findings[1]) == (
        'node3.example.com:BMC #502 2 mac addresses: '
        '#1001 aa:bb:cc:00:00:03, #1002 aa:bb:cc:00:00:04')


def test_other_interfaces_are_not_checked():
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    nb.add_interface(node1, 'swp1')

    assert BmcMacsCommand(nb).find() == []


def test_the_name_is_matched_without_regard_to_case():
    "An inconsistently cased BMC is exactly what a linter is run to find"
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    nb.add_interface(node1, 'bmc')

    assert [finding.porcelain() for finding in BmcMacsCommand(nb).find()] == [
        'node1.example.com:bmc']


def test_the_name_can_be_something_else():
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    nb.add_interface(node1, 'IPMI')
    nb.add_interface(node1, 'BMC')

    cmd = BmcMacsCommand(nb)
    cmd.set_name('IPMI')

    assert [finding.porcelain() for finding in cmd.find()] == [
        'node1.example.com:IPMI']


def test_a_mac_on_a_vm_interface_does_not_count_for_a_device_one():
    "The two ids come from different tables, so #500 twice means nothing"
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    vm1 = nb.add_vm('vm1.example.com')
    nb.add_interface(node1, 'BMC')
    nb.add_mac(
        'AA:BB:CC:00:00:01', iface=nb.add_vm_interface(vm1, 'eth0'))

    assert [finding.porcelain() for finding in BmcMacsCommand(nb).find()] == [
        'node1.example.com:BMC']


def test_an_unassigned_mac_does_not_count():
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    nb.add_interface(node1, 'BMC')
    nb.add_mac('AA:BB:CC:00:00:01')

    assert len(BmcMacsCommand(nb).find()) == 1


def test_command_reports_and_counts(capsys):
    assert BmcMacsCommand(a_netbox()).run() == 2
    assert capsys.readouterr().out == (
        '--------\n'
        'bmc-macs\n'
        '--------\n'
        '- node2.example.com:BMC #501 no mac address\n'
        '- node3.example.com:BMC #502 2 mac addresses: '
        '#1001 aa:bb:cc:00:00:03, #1002 aa:bb:cc:00:00:04\n')


def test_a_clean_netbox_is_silent(capsys):
    assert BmcMacsCommand(FakeNetbox()).run() == 0
    assert capsys.readouterr().out == ''
