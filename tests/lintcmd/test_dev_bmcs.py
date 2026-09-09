from nbtools.lintcmd.dev_bmcs import DeviceBmcsCommand
from nbtools.util import FILTER_CHUNK

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

    nb.add_mac('AA:BB:CC:00:00:01', iface=a_bmc(nb, node1))
    a_bmc(nb, node2)
    bmc3 = a_bmc(nb, node3)
    nb.add_mac('AA:BB:CC:00:00:03', iface=bmc3)
    nb.add_mac('AA:BB:CC:00:00:04', iface=bmc3)

    return nb


def a_bmc(nb, device, name='BMC'):
    "A BMC the way one is supposed to look, bar the MACs on it"
    return nb.add_interface(device, name, mgmt_only=True)


def a_device_with_an_oob_ip(nb, name, ifname='iDRAC', mac=None):
    "A device whose BMC is only recognisable by its oob_ip"
    device = nb.add_device(name)
    iface = nb.add_interface(device, ifname)
    if mac is not None:
        nb.add_mac(mac, iface=iface)

    nb.set_oob_ip(device, nb.add_ip('10.9.0.1/24', iface=iface))

    return device


def porcelain(findings):
    return [finding.porcelain() for finding in findings]


def test_a_bmc_with_exactly_one_mac_is_fine():
    findings = DeviceBmcsCommand(a_netbox()).find()

    assert 'node1.example.com:BMC' not in porcelain(findings)


def test_a_bmc_with_no_mac_is_reported():
    findings = DeviceBmcsCommand(a_netbox()).find()

    assert str(findings[0]) == 'node2.example.com:BMC #501 no mac address'


def test_a_bmc_with_two_macs_is_reported_with_both():
    findings = DeviceBmcsCommand(a_netbox()).find()

    assert str(findings[1]) == (
        'node3.example.com:BMC #502 2 mac addresses: '
        '#1001 aa:bb:cc:00:00:03, #1002 aa:bb:cc:00:00:04')


def test_other_interfaces_are_not_checked_as_bmcs():
    "swp1 is not a BMC, so what is reported is the missing BMC"
    nb = FakeNetbox()
    nb.add_interface(nb.add_device('node1.example.com'), 'swp1')

    assert [str(finding) for finding in DeviceBmcsCommand(nb).find()] == [
        'node1.example.com #400 no bmc-like interface']


def test_the_name_is_matched_without_regard_to_case():
    "An inconsistently cased BMC is exactly what a linter is run to find"
    nb = FakeNetbox()
    a_bmc(nb, nb.add_device('node1.example.com'), name='bmc')

    assert porcelain(DeviceBmcsCommand(nb).find()) == ['node1.example.com:bmc']


def test_the_name_can_be_something_else():
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    nb.add_interface(node1, 'IPMI', mgmt_only=True)
    nb.add_mac('AA:BB:CC:00:00:01', iface=a_bmc(nb, node1))

    cmd = DeviceBmcsCommand(nb)
    cmd.set_name('IPMI')

    assert porcelain(cmd.find()) == ['node1.example.com:IPMI']


def test_a_mac_on_a_vm_interface_does_not_count_for_a_device_one():
    "The two ids come from different tables, so #500 twice means nothing"
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    vm1 = nb.add_vm('vm1.example.com')
    a_bmc(nb, node1)
    nb.add_mac(
        'AA:BB:CC:00:00:01', iface=nb.add_vm_interface(vm1, 'eth0'))

    assert porcelain(DeviceBmcsCommand(nb).find()) == ['node1.example.com:BMC']


def test_an_unassigned_mac_does_not_count():
    nb = FakeNetbox()
    a_bmc(nb, nb.add_device('node1.example.com'))
    nb.add_mac('AA:BB:CC:00:00:01')

    assert len(DeviceBmcsCommand(nb).find()) == 1


# -- the mgmt_only half: the flag NetBox itself understands --

def test_a_bmc_that_is_not_flagged_mgmt_only_is_reported():
    "The name is a local convention; the flag is what NetBox reads"
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    nb.add_mac('AA:BB:CC:00:00:01', iface=nb.add_interface(node1, 'BMC'))

    assert [str(finding) for finding in DeviceBmcsCommand(nb).find()] == [
        'node1.example.com:BMC #500 mgmt_only is not set']


def test_both_faults_land_on_one_line():
    nb = FakeNetbox()
    nb.add_interface(nb.add_device('node1.example.com'), 'BMC')

    assert [str(finding) for finding in DeviceBmcsCommand(nb).find()] == [
        'node1.example.com:BMC #500 no mac address; mgmt_only is not set']


def test_a_mgmt_only_interface_is_a_bmc_whatever_its_name():
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    nb.add_interface(node1, 'ma1', mgmt_only=True)

    assert [str(finding) for finding in DeviceBmcsCommand(nb).find()] == [
        'node1.example.com:ma1 #500 no mac address']


def test_a_mgmt_only_interface_is_not_complained_about_for_its_name():
    "It is the BMC because NetBox says so, so BMC is not owed"
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    nb.add_mac(
        'AA:BB:CC:00:00:01',
        iface=nb.add_interface(node1, 'ma1', mgmt_only=True))

    assert DeviceBmcsCommand(nb).find() == []


def test_the_flag_is_only_owed_by_the_interface_named_bmc():
    "--name moves which of the two is expected to carry it"
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    nb.add_mac('AA:BB:CC:00:00:01', iface=nb.add_interface(node1, 'BMC'))
    nb.add_mac('AA:BB:CC:00:00:02', iface=nb.add_interface(node1, 'IPMI'))

    cmd = DeviceBmcsCommand(nb)
    cmd.set_name('IPMI')

    assert [str(finding) for finding in cmd.find()] == [
        'node1.example.com:IPMI #501 mgmt_only is not set']


def test_an_oob_interface_is_not_owed_the_flag():
    "Nothing here has standing to say what an iDRAC should be called"
    nb = FakeNetbox()
    a_device_with_an_oob_ip(
        nb, 'node1.example.com', 'iDRAC', mac='AA:BB:CC:00:00:01')

    assert DeviceBmcsCommand(nb).find() == []


# -- the oob_ip half: a BMC that is not called BMC --

def test_the_interface_holding_the_oob_ip_is_a_bmc_whatever_its_name():
    nb = FakeNetbox()
    a_device_with_an_oob_ip(nb, 'node1.example.com', 'iDRAC')

    assert [str(finding) for finding in DeviceBmcsCommand(nb).find()] == [
        'node1.example.com:iDRAC #500 no mac address']


def test_an_oob_interface_with_one_mac_is_fine():
    nb = FakeNetbox()
    a_device_with_an_oob_ip(
        nb, 'node1.example.com', 'iLO', mac='AA:BB:CC:00:00:01')

    assert DeviceBmcsCommand(nb).find() == []


def test_a_device_with_no_bmc_like_interface_at_all_is_reported():
    nb = FakeNetbox()
    nb.add_interface(nb.add_device('node1.example.com'), 'eth0')

    assert [str(finding) for finding in DeviceBmcsCommand(nb).find()] == [
        'node1.example.com #400 no bmc-like interface']


def test_a_device_with_no_interfaces_at_all_is_not_reported():
    "A patch panel or a PDU is a thing in a rack, not a machine"
    nb = FakeNetbox()
    nb.add_device('patch1.example.com')

    assert DeviceBmcsCommand(nb).find() == []


def test_a_chassis_with_device_bays_is_not_reported():
    "The BMCs belong to the blades, and each blade is a device here"
    nb = FakeNetbox()
    chassis = nb.add_device('chassis1.example.com', device_bays=16)
    nb.add_interface(chassis, 'mgmt0')

    assert DeviceBmcsCommand(nb).find() == []


def test_an_oob_ip_that_sits_on_nothing_is_not_a_bmc():
    "And the note says so: it is a different fault from having none"
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    nb.add_interface(node1, 'eth0')
    nb.set_oob_ip(node1, nb.add_ip('10.9.0.1/24'))

    assert [str(finding) for finding in DeviceBmcsCommand(nb).find()] == [
        'node1.example.com #400 no bmc-like interface '
        '(oob ip 10.9.0.1/24 is on no interface of this device)']


def test_an_oob_ip_on_another_devices_interface_is_not_a_bmc():
    "Otherwise the finding would be filed under the wrong machine"
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    node2 = nb.add_device('node2.example.com')
    nb.add_interface(node1, 'eth0')
    nb.add_mac('AA:BB:CC:00:00:02', iface=a_bmc(nb, node2))
    nb.set_oob_ip(node1, nb.add_ip(
        '10.9.0.2/24', iface=nb.dcim.interfaces.get(name='BMC')))

    assert [str(finding) for finding in DeviceBmcsCommand(nb).find()] == [
        'node1.example.com #400 no bmc-like interface '
        '(oob ip 10.9.0.2/24 is on no interface of this device)']


def test_an_oob_ip_on_a_vm_interface_is_not_a_bmc():
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    vm1 = nb.add_vm('vm1.example.com')
    nb.add_interface(node1, 'eth0')
    nb.set_oob_ip(node1, nb.add_ip(
        '10.9.0.3/24', iface=nb.add_vm_interface(vm1, 'eth0')))

    assert [str(finding) for finding in DeviceBmcsCommand(nb).find()] == [
        'node1.example.com #400 no bmc-like interface '
        '(oob ip 10.9.0.3/24 is on no interface of this device)']


def test_a_named_bmc_and_a_separate_oob_interface_are_both_checked():
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    a_bmc(nb, node1)
    idrac = nb.add_interface(node1, 'iDRAC')
    nb.set_oob_ip(node1, nb.add_ip('10.9.0.1/24', iface=idrac))

    assert porcelain(DeviceBmcsCommand(nb).find()) == [
        'node1.example.com:BMC', 'node1.example.com:iDRAC']


def test_an_interface_that_is_both_is_only_reported_once():
    nb = FakeNetbox()
    node1 = nb.add_device('node1.example.com')
    bmc = a_bmc(nb, node1)
    nb.set_oob_ip(node1, nb.add_ip('10.9.0.1/24', iface=bmc))

    assert porcelain(DeviceBmcsCommand(nb).find()) == ['node1.example.com:BMC']


def test_the_reads_are_chunked_rather_than_one_per_device():
    """
    More devices than fit in one filter, over the same four reads.

    FILTER_CHUNK is what splits them, and an off-by-one there would
    either drop a device or send a filter nobody can answer.
    """
    nb = FakeNetbox()
    for number in range(FILTER_CHUNK + 1):
        device = nb.add_device(f'node{number}.example.com')
        iface = a_bmc(nb, device)
        nb.set_oob_ip(device, nb.add_ip(f'10.9.0.{number}/16', iface=iface))

    assert len(DeviceBmcsCommand(nb).find()) == FILTER_CHUNK + 1


def test_the_findings_are_grouped_by_kind_and_then_ordered():
    """
    The machines with no BMC first, then the BMCs with bad MACs.

    Built in the order that comes out wrong: the device ids run the
    other way from the names, and an unsorted find() would follow
    them.
    """
    nb = FakeNetbox()
    a_bmc(nb, nb.add_device('node9.example.com'))
    nb.add_interface(nb.add_device('node5.example.com'), 'eth0')
    nb.add_interface(nb.add_device('node1.example.com'), 'eth0')

    assert [str(finding) for finding in DeviceBmcsCommand(nb).find()] == [
        'node1.example.com #402 no bmc-like interface',
        'node5.example.com #401 no bmc-like interface',
        'node9.example.com:BMC #500 no mac address']


def test_command_reports_and_counts(capsys):
    assert DeviceBmcsCommand(a_netbox()).run() == 2
    assert capsys.readouterr().out == (
        '-----------\n'
        'device-bmcs\n'
        '-----------\n'
        '- node2.example.com:BMC #501 no mac address\n'
        '- node3.example.com:BMC #502 2 mac addresses: '
        '#1001 aa:bb:cc:00:00:03, #1002 aa:bb:cc:00:00:04\n')


def test_a_clean_netbox_is_silent(capsys):
    assert DeviceBmcsCommand(FakeNetbox()).run() == 0
    assert capsys.readouterr().out == ''
