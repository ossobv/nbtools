from types import SimpleNamespace as NS

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
