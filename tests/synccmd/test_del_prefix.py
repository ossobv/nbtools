import io
import sys
from types import SimpleNamespace as NS

import pytest

from nbtools.command import ProcessMode
from nbtools.exceptions import (
    AmbiguousItem, InvalidInput, ItemNotEmpty, NotFound,
    UnrecognisedItem)
from nbtools.synccmd.del_prefix import DeletePrefixCommand
from nbtools.types import VrfPrefix

from ..nbstub import FakeNetbox


def a_netbox():
    """
    Two empty prefixes and one that holds an address.

    10.1.3.0/24 is in vrf-red and 10.1.4.0/24 in the global table, so
    between them they cover both spellings of the argument.
    """
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')

    nb.add_prefix('10.1.2.0/24', vrf=red)
    nb.add_prefix('10.1.3.0/24', vrf=red)
    nb.add_prefix('10.1.4.0/24')
    nb.add_ip('10.1.2.7/24', vrf=red)

    return nb


def a_command(nb, *args, force=False):
    cmd = DeletePrefixCommand(nb)
    cmd.set_input([VrfPrefix(arg) for arg in args])
    if force:
        cmd.set_force()
    return cmd


def prefixes_left(nb):
    return sorted(str(rec.prefix) for rec in nb.ipam.prefixes.records)


def test_the_plan_names_the_vrf_and_the_prefix():
    nb = a_netbox()
    cmd = a_command(nb, '10.1.3.0/24@vrf-red')

    assert [str(work) for work in cmd.plan()] == [
        'vrf-red del prefix 10.1.3.0/24']


def test_the_global_table_is_named_the_way_nblint_names_it():
    "The line is read by somebody confirming a delete, not by a shell"
    nb = a_netbox()
    cmd = a_command(nb, '10.1.4.0/24@')

    assert [str(work) for work in cmd.plan()] == [
        'global del prefix 10.1.4.0/24']


def test_running_it_deletes_the_record():
    nb = a_netbox()

    a_command(nb, '10.1.3.0/24@vrf-red').run(ProcessMode.YES)

    assert prefixes_left(nb) == ['10.1.2.0/24', '10.1.4.0/24']


def test_several_prefixes_go_in_one_run():
    nb = a_netbox()
    cmd = a_command(nb, '10.1.3.0/24@vrf-red', '10.1.4.0/24@')

    assert len(cmd.plan()) == 2
    cmd.run(ProcessMode.YES)
    assert prefixes_left(nb) == ['10.1.2.0/24']


def test_a_prefix_that_is_no_longer_empty_is_refused():
    "The listing that named it is older than this run"
    nb = a_netbox()

    with pytest.raises(ItemNotEmpty):
        a_command(nb, '10.1.2.0/24@vrf-red').plan()


def test_force_deletes_it_anyway():
    nb = a_netbox()

    a_command(nb, '10.1.2.0/24@vrf-red', force=True).run(ProcessMode.YES)

    assert prefixes_left(nb) == ['10.1.3.0/24', '10.1.4.0/24']


def test_a_prefix_filled_by_a_smaller_prefix_is_refused_too():
    nb = FakeNetbox()
    nb.add_prefix('10.0.0.0/8')
    nb.add_prefix('10.1.2.0/24')

    with pytest.raises(ItemNotEmpty):
        a_command(nb, '10.0.0.0/8@').plan()


def test_the_vrf_is_part_of_what_names_the_record():
    "Deleting 10.1.3.0/24 from the global table must not take vrf-red's"
    nb = a_netbox()

    with pytest.raises(NotFound):
        a_command(nb, '10.1.3.0/24@').plan()


def test_an_unknown_prefix_is_not_found():
    nb = a_netbox()

    with pytest.raises(NotFound):
        a_command(nb, '10.9.9.0/24@vrf-red').plan()


def test_an_unknown_vrf_says_so_rather_than_not_found():
    nb = a_netbox()

    with pytest.raises(UnrecognisedItem):
        a_command(nb, '10.1.3.0/24@vrf-blue').plan()


def test_a_prefix_recorded_twice_in_one_vrf_is_refused():
    "Deleting by name has to refuse rather than guess which one"
    nb = FakeNetbox()
    red = nb.add_vrf('vrf-red')
    nb.add_prefix('10.1.3.0/24', vrf=red)
    nb.add_prefix('10.1.3.0/24', vrf=red)

    with pytest.raises(AmbiguousItem):
        a_command(nb, '10.1.3.0/24@vrf-red').plan()


def test_a_prefix_argued_off_its_own_boundary_names_the_same_record():
    nb = a_netbox()

    a_command(nb, '10.1.3.7/24@vrf-red').run(ProcessMode.YES)

    assert prefixes_left(nb) == ['10.1.2.0/24', '10.1.4.0/24']


def test_nothing_to_do_is_silent(capsys):
    nb = a_netbox()

    a_command(nb).run(ProcessMode.YES)

    assert capsys.readouterr().out == 'Nothing to do\n'
    assert prefixes_left(nb) == ['10.1.2.0/24', '10.1.3.0/24', '10.1.4.0/24']


def test_the_listing_and_the_banner(capsys):
    nb = a_netbox()

    a_command(nb, '10.1.3.0/24@vrf-red').run(ProcessMode.YES)

    assert capsys.readouterr().out == (
        '-------------\n'
        'delete-prefix\n'
        '-------------\n'
        '- vrf-red del prefix 10.1.3.0/24\n')


# -- how the values get in --

def from_args(nb, prefixes, batch=False, force=False):
    "Build it the way nbsync does, from a parsed argument namespace"
    return DeletePrefixCommand.from_args(
        nb, NS(prefix=prefixes, batch=batch, force=force))


def test_xargs_style_arguments_need_nothing_special():
    nb = a_netbox()
    cmd = from_args(nb, [VrfPrefix('10.1.3.0/24@vrf-red')])

    assert [str(work) for work in cmd.plan()] == [
        'vrf-red del prefix 10.1.3.0/24']


def test_a_dash_reads_the_values_from_stdin(monkeypatch, capsys):
    nb = a_netbox()
    monkeypatch.setattr(sys, 'stdin', io.StringIO(
        '10.1.3.0/24@vrf-red\n'
        '10.1.4.0/24@\n'))

    from_args(nb, ['-'], batch=True).run(ProcessMode.YES)

    assert capsys.readouterr().out == (
        '- vrf-red del prefix 10.1.3.0/24\n'
        '- global del prefix 10.1.4.0/24\n')
    assert prefixes_left(nb) == ['10.1.2.0/24']


def test_stdin_deletes_each_prefix_as_it_arrives(monkeypatch):
    """
    The stream is not read ahead: the first delete lands before the
    second line is looked at.
    """
    nb = a_netbox()
    read = []

    class Watched(io.StringIO):
        def __next__(self):
            line = super().__next__()
            read.append((line.strip(), prefixes_left(nb)))
            return line

    monkeypatch.setattr(sys, 'stdin', Watched(
        '10.1.3.0/24@vrf-red\n'
        '10.1.4.0/24@\n'))

    from_args(nb, ['-'], batch=True).run(ProcessMode.YES)

    assert read == [
        # Nothing deleted yet when the first line is read...
        ('10.1.3.0/24@vrf-red',
         ['10.1.2.0/24', '10.1.3.0/24', '10.1.4.0/24']),
        # ...and the first one is gone before the second is.
        ('10.1.4.0/24@', ['10.1.2.0/24', '10.1.4.0/24'])]
    assert prefixes_left(nb) == ['10.1.2.0/24']


def test_stdin_ignores_blank_lines(monkeypatch):
    nb = a_netbox()
    monkeypatch.setattr(sys, 'stdin', io.StringIO(
        '\n10.1.3.0/24@vrf-red\n\n'))

    from_args(nb, ['-'], batch=True).run(ProcessMode.YES)

    assert prefixes_left(nb) == ['10.1.2.0/24', '10.1.4.0/24']


def test_stdin_mixes_with_arguments(monkeypatch):
    "The value typed goes first, then the stream it stands beside"
    nb = a_netbox()
    monkeypatch.setattr(sys, 'stdin', io.StringIO('10.1.4.0/24@\n'))

    cmd = from_args(
        nb, [VrfPrefix('10.1.3.0/24@vrf-red'), '-'], batch=True)
    cmd.run(ProcessMode.YES)

    assert prefixes_left(nb) == ['10.1.2.0/24']


def test_stdin_without_batch_is_refused(monkeypatch, capsys):
    """
    The confirmation would have to read that same stdin

    The refusal lives in SyncCommand.confirm_or_die(), so this checks
    that delete-prefix is wired into it rather than checking the rule
    itself -- tests/test_command.py does that.
    """
    nb = a_netbox()
    monkeypatch.setattr(sys, 'stdin', io.StringIO('10.1.3.0/24@vrf-red\n'))

    cmd = from_args(nb, ['-'], batch=True)

    with pytest.raises(SystemExit) as caught:
        cmd.run(ProcessMode.INTERACTIVE)

    assert caught.value.code == 3
    assert '--batch' in capsys.readouterr().err
    assert prefixes_left(nb) == ['10.1.2.0/24', '10.1.3.0/24', '10.1.4.0/24']


def test_a_bad_line_on_stdin_is_rejected(monkeypatch):
    "When it is reached, stdin being read lazily"
    nb = a_netbox()
    monkeypatch.setattr(sys, 'stdin', io.StringIO('not-a-prefix\n'))

    with pytest.raises(InvalidInput):
        from_args(nb, ['-'], batch=True).run(ProcessMode.YES)


def test_keep_going_carries_on_past_a_prefix_that_is_gone(monkeypatch):
    "A porcelain listing goes stale, and a feed of them is long"
    nb = a_netbox()
    monkeypatch.setattr(sys, 'stdin', io.StringIO(
        '10.9.9.0/24@vrf-red\n'
        '10.1.3.0/24@vrf-red\n'))

    cmd = from_args(nb, ['-'], batch=True)
    cmd.set_keep_going()

    assert cmd.run(ProcessMode.YES) == 1
    assert prefixes_left(nb) == ['10.1.2.0/24', '10.1.4.0/24']
