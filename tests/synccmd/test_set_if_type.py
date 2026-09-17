import io
import sys

import pytest

from nbtools.command import ProcessMode, STDIN_ARG
from nbtools.exceptions import UnrecognisedItemOnTarget
from nbtools.synccmd.set_if_type import SetInterfaceTypeCommand
from nbtools.types import DevIface

from ..nbstub import FakeNetbox


def a_netbox():
    nb = FakeNetbox()
    pve1 = nb.add_device('pve1.example.com')
    nb.add_interface(pve1, 'vmbr0', type_='bridge')
    nb.add_interface(pve1, 'vmbr1', type_='1000base-t')
    nb.add_interface(pve1, 'vmbr2', type_='virtual')
    return nb


def a_command(nb, *targets, type_='bridge'):
    cmd = SetInterfaceTypeCommand(nb)
    cmd.set_type(type_)
    cmd.set_input_values(list(targets), DevIface)
    return cmd


def types_of(nb):
    return {
        iface.name: iface.type.value for iface in nb.dcim.interfaces.all()}


def test_an_interface_gets_the_type():
    nb = a_netbox()
    cmd = a_command(
        nb, DevIface('pve1.example.com:vmbr1'),
        DevIface('pve1.example.com:vmbr2'))

    work = cmd.plan()
    assert [str(future) for future in work] == [
        'pve1.example.com set int vmbr1 type=bridge',
        'pve1.example.com set int vmbr2 type=bridge']

    for future in work:
        future.do(nb)

    assert types_of(nb) == {
        'vmbr0': 'bridge', 'vmbr1': 'bridge', 'vmbr2': 'bridge'}
    assert nb.dcim.interfaces.updated == [
        {'type': 'bridge', 'id': 501}, {'type': 'bridge', 'id': 502}]


def test_an_interface_that_has_the_type_is_no_work():
    cmd = a_command(a_netbox(), DevIface('pve1.example.com:vmbr0'))

    assert cmd.plan() == []


def test_an_unknown_interface_is_refused():
    cmd = a_command(a_netbox(), DevIface('pve1.example.com:vmbr9'))

    with pytest.raises(UnrecognisedItemOnTarget):
        cmd.plan()


def test_the_targets_can_come_off_stdin(monkeypatch, capsys):
    "The shape of nblint --porcelain interface-types ... | nbsync ... -"
    monkeypatch.setattr(sys, 'stdin', io.StringIO(
        'pve1.example.com:vmbr1\n'
        'pve1.example.com:vmbr0\n'
        'pve1.example.com:vmbr2\n'))
    nb = a_netbox()
    cmd = a_command(nb, STDIN_ARG)

    assert cmd.run(ProcessMode.YES) == 0
    assert capsys.readouterr().out == (
        '- pve1.example.com set int vmbr1 type=bridge\n'
        '- pve1.example.com set int vmbr2 type=bridge\n')
    assert set(types_of(nb).values()) == {'bridge'}
