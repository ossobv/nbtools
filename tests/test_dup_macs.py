from types import SimpleNamespace as NS

from nbtools.lintcmd.dup_macs import (
    DuplicateMacFinding, DuplicateMacsCommand, get_duplicate_macs)

from .nbstub import a_mac, a_vm_iface, an_iface, an_nbapi


BMC = an_iface('BMC', 'node1.example.com')
MAC = 'AA:BB:CC:00:00:01'


def a_finding(nbapi):
    duplicates = get_duplicate_macs(nbapi)
    assert len(duplicates) == 1, duplicates
    return DuplicateMacFinding(duplicates[0])


def test_a_mac_recorded_once_is_not_a_duplicate():
    nbapi = an_nbapi(a_mac(1, MAC, BMC), a_mac(2, 'AA:BB:CC:00:00:02'))

    assert get_duplicate_macs(nbapi) == []


def test_duplicates_are_grouped_and_split():
    nbapi = an_nbapi(
        a_mac(1, MAC, BMC), a_mac(2, MAC), a_mac(3, 'AA:BB:CC:00:00:09'))

    duplicates = get_duplicate_macs(nbapi)
    assert len(duplicates) == 1
    assert duplicates[0].mac == 'aa:bb:cc:00:00:01'
    assert [rec.id for rec in duplicates[0].assigned] == [1]
    assert [rec.id for rec in duplicates[0].unassigned] == [2]


def test_grouping_ignores_case():
    "NetBox hands back upper case; the q= lookups use lower"
    nbapi = an_nbapi(a_mac(1, MAC, BMC), a_mac(2, 'aa:bb:cc:00:00:01'))

    assert [dup.mac for dup in get_duplicate_macs(nbapi)] == [
        'aa:bb:cc:00:00:01']


def test_placeholder_macs_are_not_identities():
    "NetBox fills these in when something is unknown"
    nbapi = an_nbapi(
        a_mac(1, '00:00:00:00:00:00', BMC), a_mac(2, '00:00:00:00:00:00'),
        a_mac(3, 'FF:FF:FF:FF:FF:FF'), a_mac(4, 'FF:FF:FF:FF:FF:FF'))

    assert get_duplicate_macs(nbapi) == []


def test_one_device_sharing_a_mac_is_explained():
    "A bridge and its members, or a parent and its subinterfaces"
    bridge = an_iface('br0', 'node1.example.com', id_=10)
    member = an_iface('swp1', 'node1.example.com', id_=11)
    nbapi = an_nbapi(a_mac(1, MAC, bridge), a_mac(2, MAC, member))

    assert a_finding(nbapi).duplicate.is_explained
    assert DuplicateMacsCommand(nbapi).find() == []


def test_two_records_on_one_interface_is_not_explained():
    "However it happened, one interface does not need two of them"
    nbapi = an_nbapi(a_mac(1, MAC, BMC), a_mac(2, MAC, BMC))

    assert not a_finding(nbapi).duplicate.is_explained


def test_one_virtual_machine_sharing_a_mac_is_explained():
    "A vminterface has .virtual_machine and no .device at all"
    one = a_vm_iface('eth0', 'vm1.example.com', id_=10)
    two = a_vm_iface('eth1', 'vm1.example.com', id_=11)
    nbapi = an_nbapi(a_mac(1, MAC, one), a_mac(2, MAC, two))

    assert a_finding(nbapi).duplicate.is_explained


def test_a_device_and_a_virtual_machine_are_not_one_machine():
    "Their ids come from different tables, so #538 twice means nothing"
    vm_iface = a_vm_iface('eth0', 'vm1.example.com', id_=99, vmid=538)
    nbapi = an_nbapi(a_mac(1, MAC, BMC), a_mac(2, MAC, vm_iface))

    assert not a_finding(nbapi).duplicate.is_explained


def test_finding_names_the_virtual_machine():
    vm_iface = a_vm_iface('eth0', 'vm1.example.com')
    nbapi = an_nbapi(a_mac(1, MAC, vm_iface), a_mac(2, MAC))

    assert str(a_finding(nbapi)) == (
        'aa:bb:cc:00:00:01 x2: #1 vm1.example.com:eth0, #2 unassigned')


def test_an_interface_shaped_like_neither_is_not_explained():
    "Do not vouch for something we cannot place"
    odd = NS(id=1, name='eth0')
    nbapi = an_nbapi(a_mac(1, MAC, odd), a_mac(2, MAC, odd))

    assert not a_finding(nbapi).duplicate.is_explained


def test_two_devices_sharing_a_mac_is_not_explained():
    "A NIC moved without anyone cleaning up behind it"
    other = an_iface('BMC', 'node2.example.com', id_=20, devid=539)
    nbapi = an_nbapi(a_mac(1, MAC, BMC), a_mac(2, MAC, other))

    assert not a_finding(nbapi).duplicate.is_explained


def test_an_unassigned_copy_is_never_explained():
    nbapi = an_nbapi(a_mac(1, MAC, BMC), a_mac(2, MAC))

    assert not a_finding(nbapi).duplicate.is_explained


def test_finding_lists_every_copy_and_where_it_sits():
    nbapi = an_nbapi(a_mac(1, MAC, BMC), a_mac(2, MAC))

    finding = a_finding(nbapi)
    assert str(finding) == (
        'aa:bb:cc:00:00:01 x2: #1 node1.example.com:BMC, #2 unassigned')
    assert finding.porcelain() == 'aa:bb:cc:00:00:01'


def test_finding_quotes_a_device_name_with_spaces():
    spaced = an_iface('BMC', 'FREE (was-planned: node3.example.com)')
    nbapi = an_nbapi(a_mac(1, MAC, spaced), a_mac(2, MAC))

    assert str(a_finding(nbapi)) == (
        "aa:bb:cc:00:00:01 x2: "
        "#1 'FREE (was-planned: node3.example.com)':BMC, #2 unassigned")


def test_finding_says_when_no_copy_is_assigned():
    "Cleaning that one up drops the MAC from NetBox altogether"
    nbapi = an_nbapi(a_mac(1, MAC), a_mac(2, MAC))

    assert str(a_finding(nbapi)) == (
        'aa:bb:cc:00:00:01 x2: #1 unassigned, #2 unassigned'
        ' (none assigned)')


def test_command_reports_and_counts(capsys):
    nbapi = an_nbapi(a_mac(1, MAC, BMC), a_mac(2, MAC))

    assert DuplicateMacsCommand(nbapi).run() == 1
    assert capsys.readouterr().out == (
        '--------------\n'
        'duplicate-macs\n'
        '--------------\n'
        '- aa:bb:cc:00:00:01 x2: #1 node1.example.com:BMC, #2 unassigned\n')


def test_command_all_reports_the_explained_ones_too(capsys):
    bridge = an_iface('br0', 'node1.example.com', id_=10)
    member = an_iface('swp1', 'node1.example.com', id_=11)
    nbapi = an_nbapi(a_mac(1, MAC, bridge), a_mac(2, MAC, member))

    cmd = DuplicateMacsCommand(nbapi)
    cmd.set_report_all()

    assert cmd.run() == 1
    assert capsys.readouterr().out.endswith(
        '- aa:bb:cc:00:00:01 x2: #1 node1.example.com:br0, '
        '#2 node1.example.com:swp1 (shared within one device)\n')


def test_command_limit_unassigned_drops_the_rest(capsys):
    "The cross-machine one is real, but unset-interface-mac cannot help"
    elsewhere = 'AA:BB:CC:00:00:09'
    other = an_iface('BMC', 'node2.example.com', id_=20, devid=539)
    nbapi = an_nbapi(
        a_mac(1, MAC, BMC), a_mac(2, MAC),
        a_mac(3, elsewhere, BMC), a_mac(4, elsewhere, other))

    cmd = DuplicateMacsCommand(nbapi)
    cmd.set_limit('unassigned')

    assert [str(finding) for finding in cmd.find()] == [
        'aa:bb:cc:00:00:01 x2: #1 node1.example.com:BMC, #2 unassigned']


def test_command_limit_unassigned_keeps_the_none_assigned_ones():
    nbapi = an_nbapi(a_mac(1, MAC), a_mac(2, MAC))

    cmd = DuplicateMacsCommand(nbapi)
    cmd.set_limit('unassigned')

    assert len(cmd.find()) == 1


def test_command_limit_unassigned_ignores_all():
    "A group holding an unassigned copy is never explained anyway"
    bridge = an_iface('br0', 'node1.example.com', id_=10)
    member = an_iface('swp1', 'node1.example.com', id_=11)
    nbapi = an_nbapi(a_mac(1, MAC, bridge), a_mac(2, MAC, member))

    cmd = DuplicateMacsCommand(nbapi)
    cmd.set_limit('unassigned')
    cmd.set_report_all()

    assert cmd.find() == []


def test_command_porcelain_prints_bare_macs(capsys):
    "One value per line, no banner, so it can be piped into nbsync"
    other = 'AA:BB:CC:00:00:09'
    nbapi = an_nbapi(
        a_mac(1, MAC, BMC), a_mac(2, MAC),
        a_mac(3, other, BMC), a_mac(4, other))

    cmd = DuplicateMacsCommand(nbapi)
    cmd.set_porcelain()

    assert cmd.run() == 2
    assert capsys.readouterr().out == (
        'aa:bb:cc:00:00:01\n'
        'aa:bb:cc:00:00:09\n')


def test_command_is_silent_when_clean(capsys):
    nbapi = an_nbapi(a_mac(1, MAC, BMC))

    assert DuplicateMacsCommand(nbapi).run() == 0
    assert capsys.readouterr().out == ''
