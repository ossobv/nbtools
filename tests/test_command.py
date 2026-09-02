"""
The shared half of a sync command: its input, and the confirmation.

Values can arrive on stdin instead of as arguments, and then they are
planned and done one item at a time as they land -- which is what
stdin is for, over "| xargs -L1 COMMAND" that waits for the whole
list. It also takes stdin away from the confirmation, so --batch
becomes mandatory.
"""
import io
import sys

import pytest

from nbtools.command import ProcessMode, STDIN_ARG, SyncCommand, stdin_or
from nbtools.exceptions import InvalidInput


class NoteWork:
    "A work item that logs when it runs, and touches no API"

    def __init__(self, name, log):
        self.name = name
        self.log = log

    def __str__(self):
        return f'note {self.name}'

    def do(self, nbapi):
        self.log.append(f'did {self.name}')


def row(*values):
    "The row type for these tests: the values, as they came"
    return values


class ACommand(SyncCommand):
    "The smallest sync command: one work item per row it was given"
    name = 'a-command'
    help = 'For the tests.'

    def __init__(self, nbapi=None):
        super().__init__(nbapi)
        self.log = []

    def prepare(self):
        self.log.append('prepared')

    def plan_one(self, value):
        name = ' '.join(str(field) for field in value)
        self.log.append(f'planned {name}')
        return [NoteWork(name, self.log)]


def as_int(text):
    "A type_func with a name, to check stdin_or borrows it"
    return int(text)


def on_stdin(monkeypatch, text):
    monkeypatch.setattr(sys, 'stdin', io.StringIO(text))


def slots(*values, type_func=as_int):
    "One slot per value, all of them read the same way"
    return [(value, type_func) for value in values]


def a_command(monkeypatch, arg_slots, stdin=''):
    "A command whose input came from these slots, stdin holding that"
    on_stdin(monkeypatch, stdin)
    cmd = ACommand()
    cmd.set_input_rows(row, arg_slots)
    return cmd


# -- stdin_or, the argparse side --

def test_stdin_or_passes_the_dash_through():
    assert stdin_or(as_int)(STDIN_ARG) == STDIN_ARG


def test_stdin_or_applies_the_type_to_anything_else():
    assert stdin_or(as_int)('42') == 42


def test_stdin_or_still_raises_on_a_bad_value():
    "argparse turns a ValueError from type= into a usage message"
    with pytest.raises(ValueError):
        stdin_or(as_int)('nonsense')


def test_stdin_or_names_itself_after_what_it_wraps():
    "argparse prints the type's name in some of its errors"
    assert stdin_or(as_int).__name__ == 'as_int_or_stdin'


def test_stdin_or_survives_a_type_without_a_name():
    assert stdin_or(int).__name__ == 'int_or_stdin'


# -- set_input_rows --

def parsed(arg_slots, line):
    "The row that one line of stdin makes, for these slots"
    cmd = ACommand()
    cmd.set_input_rows(row, arg_slots)
    return cmd._parse_row(line)


def test_arguments_without_a_dash_are_the_one_row():
    cmd = ACommand()
    cmd.set_input_rows(row, slots(1, 2))

    assert list(cmd._input) == [(1, 2)]


def test_arguments_without_a_dash_leave_stdin_alone():
    "Which is what lets the confirmation still ask"
    cmd = ACommand()
    cmd.set_input_rows(row, slots(1, 2))

    assert not cmd._stdin_is_input


def test_a_dash_takes_stdin():
    cmd = ACommand()
    cmd.set_input_rows(row, slots(STDIN_ARG))

    assert cmd._stdin_is_input


def test_a_dash_reads_nothing_until_the_run(monkeypatch):
    "The laziness is the point: it is what lets run() interleave"
    stdin = io.StringIO('1\n2\n')
    monkeypatch.setattr(sys, 'stdin', stdin)

    ACommand().set_input_rows(row, slots(STDIN_ARG))

    assert stdin.tell() == 0


def test_two_dashes_take_two_values_from_the_line():
    assert parsed(slots(STDIN_ARG, STDIN_ARG), '1 2') == (1, 2)


def test_the_type_is_applied_per_field():
    assert parsed([(STDIN_ARG, str), (STDIN_ARG, as_int)], 'a 1') == ('a', 1)


def test_a_value_given_as_an_argument_is_kept_on_every_row():
    "Mixing them: the fixed value here, the varying one per line"
    assert parsed(slots(1, STDIN_ARG), '2') == (1, 2)


def test_one_dash_takes_the_whole_line_spaces_and_all():
    "A single value is not split: device names hold spaces"
    line = 'FREE (was: node3):BMC'

    assert parsed([(STDIN_ARG, str)], line) == (line,)


def test_the_leftmost_dash_takes_the_extra_whitespace():
    "Split from the right, so the last value ends the line"
    row_slots = [(STDIN_ARG, str), (STDIN_ARG, as_int)]

    assert parsed(row_slots, 'FREE (was: node3):BMC 42') == (
        'FREE (was: node3):BMC', 42)


def test_a_line_short_of_a_value_is_refused():
    with pytest.raises(InvalidInput):
        parsed(slots(STDIN_ARG, STDIN_ARG), '1')


def test_a_bad_value_is_refused_where_argparse_would_have():
    with pytest.raises(InvalidInput):
        parsed(slots(STDIN_ARG), 'nonsense')


def test_a_refused_line_says_which_one_it_was():
    with pytest.raises(InvalidInput, match='nonsense'):
        parsed(slots(STDIN_ARG), 'nonsense')


def test_blank_lines_are_dropped(monkeypatch):
    cmd = a_command(monkeypatch, slots(STDIN_ARG), '\n1\n\n  \n2\n')
    cmd.run(ProcessMode.YES)

    assert cmd.log == [
        'prepared', 'planned 1', 'did 1', 'planned 2', 'did 2']


def test_an_empty_stdin_takes_it_all_the_same(monkeypatch):
    "It was read either way, so the answer cannot come from there"
    cmd = a_command(monkeypatch, slots(STDIN_ARG), '')

    assert cmd._stdin_is_input


# -- plan(), and what a command has to implement --

def test_a_command_with_neither_plan_nor_input_says_so():
    class Empty(SyncCommand):
        name = 'empty'

    with pytest.raises(NotImplementedError):
        Empty(None).plan()


def test_plan_joins_up_what_plan_one_returns():
    cmd = ACommand()
    cmd.set_input([row(1), row(2)])

    assert [str(work) for work in cmd.plan()] == ['note 1', 'note 2']


def test_plan_prepares_once_for_all_the_items():
    cmd = ACommand()
    cmd.set_input([row(1), row(2)])
    cmd.plan()

    assert cmd.log.count('prepared') == 1


# -- run(), streaming --

def test_each_value_is_done_before_the_next_is_read(monkeypatch):
    "The whole point: work goes out while the input is still coming"
    cmd = a_command(monkeypatch, slots(STDIN_ARG), '1\n2\n3\n')
    cmd.run(ProcessMode.YES)

    assert cmd.log == [
        'prepared',
        'planned 1', 'did 1',
        'planned 2', 'did 2',
        'planned 3', 'did 3']


def test_a_two_value_line_is_one_item(monkeypatch):
    cmd = a_command(monkeypatch, slots(STDIN_ARG, STDIN_ARG), '1 2\n3 4\n')
    cmd.run(ProcessMode.YES)

    assert cmd.log == [
        'prepared',
        'planned 1 2', 'did 1 2',
        'planned 3 4', 'did 3 4']


def test_streaming_prepares_once_however_long_the_input(monkeypatch):
    "A read that does not depend on the item is not per item"
    cmd = a_command(monkeypatch, slots(STDIN_ARG), '1\n2\n3\n')
    cmd.run(ProcessMode.YES)

    assert cmd.log.count('prepared') == 1


def test_the_batch_path_plans_everything_first(monkeypatch):
    "Which is the difference, and why an error there changes nothing"
    cmd = a_command(monkeypatch, slots(1))
    cmd.run(ProcessMode.YES)

    assert cmd.log == ['prepared', 'planned 1', 'did 1']


def test_streaming_lists_each_item_as_it_goes(monkeypatch, capsys):
    cmd = a_command(monkeypatch, slots(STDIN_ARG), '1\n2\n')
    cmd.run(ProcessMode.YES)

    assert capsys.readouterr().out == (
        '---------\n'
        'a-command\n'
        '---------\n'
        '- note 1\n'
        '- note 2\n')


def test_streaming_an_empty_input_says_nothing_to_do(monkeypatch, capsys):
    cmd = a_command(monkeypatch, slots(STDIN_ARG), '')
    cmd.run(ProcessMode.YES)

    assert capsys.readouterr().out == 'Nothing to do\n'


def test_streaming_prints_no_banner_for_an_empty_input(monkeypatch, capsys):
    "The banner waits for the first item, there being nothing to count"
    cmd = a_command(monkeypatch, slots(STDIN_ARG), '')
    cmd.run(ProcessMode.YES)

    assert 'a-command' not in capsys.readouterr().out


def test_streaming_leaves_the_earlier_items_done(monkeypatch):
    "The trade-off: the batch path would have changed nothing"
    cmd = a_command(monkeypatch, slots(STDIN_ARG), '1\nnonsense\n3\n')

    with pytest.raises(InvalidInput):
        cmd.run(ProcessMode.YES)

    assert cmd.log == ['prepared', 'planned 1', 'did 1']


def test_the_batch_path_would_have_changed_nothing(monkeypatch):
    cmd = a_command(monkeypatch, slots(1, 2))
    cmd.plan_one = lambda value: 1 / 0

    with pytest.raises(ZeroDivisionError):
        cmd.run(ProcessMode.YES)

    assert cmd.log == ['prepared']


# -- confirm_or_die --

def test_a_command_whose_input_is_stdin_refuses_to_ask(monkeypatch, capsys):
    cmd = a_command(monkeypatch, slots(STDIN_ARG), '1\n')

    with pytest.raises(SystemExit) as caught:
        cmd.run(ProcessMode.INTERACTIVE)

    assert caught.value.code == 3
    assert '--batch' in capsys.readouterr().err


def test_the_refusal_happens_before_anything_is_done(monkeypatch):
    cmd = a_command(monkeypatch, slots(STDIN_ARG), '1\n')

    with pytest.raises(SystemExit):
        cmd.run(ProcessMode.INTERACTIVE)

    assert cmd.log == []


def test_the_refusal_does_not_even_read_stdin(monkeypatch):
    "It is a guard, not a reaction to what arrived"
    stdin = io.StringIO('1\n')
    monkeypatch.setattr(sys, 'stdin', stdin)
    cmd = ACommand()
    cmd.set_input_rows(row, slots(STDIN_ARG))

    with pytest.raises(SystemExit):
        cmd.run(ProcessMode.INTERACTIVE)

    assert stdin.tell() == 0


def test_values_on_the_command_line_still_get_the_question(monkeypatch):
    "The ordinary path: answer typed in, stdin never taken"
    cmd = a_command(monkeypatch, slots(1))
    monkeypatch.setattr('builtins.input', lambda: 'yes')
    cmd.run(ProcessMode.INTERACTIVE)

    assert cmd.log == ['prepared', 'planned 1', 'did 1']


def test_process_mode_no_still_aborts(capsys):
    "Unchanged by any of this"
    cmd = ACommand()
    cmd.set_input([row(1)])

    with pytest.raises(SystemExit) as caught:
        cmd.run(ProcessMode.NO)

    assert caught.value.code == 3
    assert 'Aborted' in capsys.readouterr().err
