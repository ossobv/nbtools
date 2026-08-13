from types import SimpleNamespace as NS

from nbtools.lintcmd.dup_macs import (
    DuplicateMacFinding, DuplicateMacsCommand)
from nbtools.netbox import get_duplicate_macs


def an_iface(name, devname):
    return NS(name=name, device=NS(name=devname))


def a_mac(id_, value, iface=None):
    "Stand in for a pynetbox dcim.mac_addresses record"
    return NS(id=id_, mac_address=value, assigned_object=iface)


def an_nbapi(*macs):
    def matching(q=None, **kwargs):
        # Stand in for the freeform q= search, substring and all.
        return [
            mac for mac in macs
            if q is None or q.lower() in str(mac.mac_address).lower()]

    return NS(dcim=NS(mac_addresses=NS(
        all=(lambda: list(macs)), filter=matching)))


BMC = an_iface('BMC', 'node1.example.com')


def test_a_mac_recorded_once_is_not_a_duplicate():
    nbapi = an_nbapi(
        a_mac(1, 'AA:BB:CC:00:00:01', BMC),
        a_mac(2, 'AA:BB:CC:00:00:02'))

    assert get_duplicate_macs(nbapi) == []


def test_duplicates_are_grouped_and_split():
    nbapi = an_nbapi(
        a_mac(1, 'AA:BB:CC:00:00:01', BMC),
        a_mac(2, 'AA:BB:CC:00:00:01'),
        a_mac(3, 'AA:BB:CC:00:00:09'))

    duplicates = get_duplicate_macs(nbapi)
    assert len(duplicates) == 1
    assert duplicates[0].mac == 'aa:bb:cc:00:00:01'
    assert [rec.id for rec in duplicates[0].assigned] == [1]
    assert [rec.id for rec in duplicates[0].unassigned] == [2]


def test_grouping_ignores_case():
    "NetBox hands back upper case; the q= lookups use lower"
    nbapi = an_nbapi(
        a_mac(1, 'AA:BB:CC:00:00:01', BMC),
        a_mac(2, 'aa:bb:cc:00:00:01'))

    assert [dup.mac for dup in get_duplicate_macs(nbapi)] == [
        'aa:bb:cc:00:00:01']


def test_finding_lists_every_copy_and_where_it_sits():
    nbapi = an_nbapi(
        a_mac(1, 'AA:BB:CC:00:00:01', BMC),
        a_mac(2, 'AA:BB:CC:00:00:01'))

    finding = DuplicateMacFinding(get_duplicate_macs(nbapi)[0])
    assert str(finding) == (
        'aa:bb:cc:00:00:01 x2: #1 node1.example.com:BMC, #2 unassigned')
    assert finding.porcelain() == 'aa:bb:cc:00:00:01'


def test_finding_quotes_a_device_name_with_spaces():
    spaced = an_iface('BMC', 'FREE (was-planned: node3.example.com)')
    nbapi = an_nbapi(
        a_mac(1, 'AA:BB:CC:00:00:01', spaced),
        a_mac(2, 'AA:BB:CC:00:00:01'))

    finding = DuplicateMacFinding(get_duplicate_macs(nbapi)[0])
    assert str(finding) == (
        "aa:bb:cc:00:00:01 x2: "
        "#1 'FREE (was-planned: node3.example.com)':BMC, #2 unassigned")


def test_finding_says_when_no_copy_is_assigned():
    "Cleaning that one up drops the MAC from NetBox altogether"
    nbapi = an_nbapi(
        a_mac(1, 'AA:BB:CC:00:00:01'),
        a_mac(2, 'AA:BB:CC:00:00:01'))

    finding = DuplicateMacFinding(get_duplicate_macs(nbapi)[0])
    assert str(finding) == (
        'aa:bb:cc:00:00:01 x2: #1 unassigned, #2 unassigned'
        ' (none assigned)')


def test_command_reports_and_counts(capsys):
    nbapi = an_nbapi(
        a_mac(1, 'AA:BB:CC:00:00:01', BMC),
        a_mac(2, 'AA:BB:CC:00:00:01'))

    assert DuplicateMacsCommand(nbapi).run() == 1
    assert capsys.readouterr().out == (
        '--------------\n'
        'duplicate-macs\n'
        '--------------\n'
        '- aa:bb:cc:00:00:01 x2: #1 node1.example.com:BMC, #2 unassigned\n')


def test_command_porcelain_prints_bare_macs(capsys):
    "One value per line, no banner, so it can be piped into nbsync"
    nbapi = an_nbapi(
        a_mac(1, 'AA:BB:CC:00:00:01', BMC),
        a_mac(2, 'AA:BB:CC:00:00:01'),
        a_mac(3, 'AA:BB:CC:00:00:09'),
        a_mac(4, 'AA:BB:CC:00:00:09'))

    check = DuplicateMacsCommand(nbapi)
    check.set_porcelain()

    assert check.run() == 2
    assert capsys.readouterr().out == (
        'aa:bb:cc:00:00:01\n'
        'aa:bb:cc:00:00:09\n')


def test_command_is_silent_when_clean(capsys):
    nbapi = an_nbapi(a_mac(1, 'AA:BB:CC:00:00:01', BMC))

    assert DuplicateMacsCommand(nbapi).run() == 0
    assert capsys.readouterr().out == ''
