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
from nbtools.exceptions import InvalidInput, UnrecognisedItem


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


class AFussyCommand(ACommand):
    "Refuses the value 13, the way a command refuses an unknown MAC"

    def plan_one(self, value):
        if 13 in value:
            raise UnrecognisedItem(value[0])

        return super().plan_one(value)


class OneValue:
    """
    plan_one() taking the value itself, as set_input_values() hands it

    Wrapped back into a row of one so that the row-shaped commands
    above can be reused for the list-shaped input.
    """
    def plan_one(self, value):
        return super().plan_one((value,))


class AListCommand(OneValue, ACommand):
    "The smallest command taking a list of values rather than a row"


class AFussyListCommand(OneValue, AFussyCommand):
    "The same, still refusing 13"


def a_command(monkeypatch, arg_slots, stdin='', cls=ACommand):
    "A command whose input came from these slots, stdin holding that"
    on_stdin(monkeypatch, stdin)
    cmd = cls()
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


def test_an_empty_stdin_takes_it_all_the_same(monkeypatch):
    "It was read either way, so the answer cannot come from there"
    cmd = a_command(monkeypatch, slots(STDIN_ARG), '')

    assert cmd._stdin_is_input


# -- set_input_values --

def a_list_command(monkeypatch, values, stdin='', cls=AListCommand):
    "A command whose input is a list of values, stdin holding that"
    on_stdin(monkeypatch, stdin)
    cmd = cls()
    cmd.set_input_values(values, as_int)
    return cmd


def test_values_without_a_dash_are_the_input():
    cmd = ACommand()
    cmd.set_input_values([1, 2], as_int)

    assert list(cmd._input) == [1, 2]


def test_values_without_a_dash_leave_stdin_alone():
    cmd = ACommand()
    cmd.set_input_values([1, 2], as_int)

    assert not cmd._stdin_is_input


def test_a_dash_among_the_values_takes_stdin():
    cmd = ACommand()
    cmd.set_input_values([STDIN_ARG], as_int)

    assert cmd._stdin_is_input


def test_a_value_is_a_whole_line_spaces_and_all():
    "A list takes one value per line, so there is nothing to split"
    cmd = ACommand()
    cmd.set_input_values([STDIN_ARG], str)

    assert cmd._parse_row('FREE (was: node3):BMC') == 'FREE (was: node3):BMC'


def test_the_value_arrives_as_itself_not_as_a_row(monkeypatch):
    "plan_one() sees the value, not a tuple of one"
    cmd = a_list_command(monkeypatch, [STDIN_ARG], '1\n')
    cmd.plan_one = lambda value: [NoteWork(repr(value), cmd.log)]
    cmd.run(ProcessMode.YES)

    assert cmd.log == ['prepared', 'did 1']


def test_a_bad_value_in_the_stream_is_refused(monkeypatch):
    cmd = a_list_command(monkeypatch, [STDIN_ARG], 'nonsense\n')

    with pytest.raises(InvalidInput):
        cmd.run(ProcessMode.YES)


def test_a_blank_line_is_no_item(monkeypatch):
    "A feed may space its output out; that is not a bad line"
    cmd = a_list_command(monkeypatch, [STDIN_ARG], '\n1\n\n2\n')
    cmd.run(ProcessMode.YES)

    assert cmd.log == [
        'prepared', 'planned 1', 'did 1', 'planned 2', 'did 2']


def test_values_typed_beside_a_dash_are_items_too(monkeypatch):
    "Where a row's other slots are constants, a list's are items"
    cmd = a_list_command(monkeypatch, [1, STDIN_ARG], '2\n3\n')
    cmd.run(ProcessMode.YES)

    assert cmd.log == [
        'prepared',
        'planned 1', 'did 1',
        'planned 2', 'did 2',
        'planned 3', 'did 3']


def test_a_second_dash_stands_for_nothing(monkeypatch):
    "The first one took stdin; there is no second stream to read"
    cmd = a_list_command(monkeypatch, [STDIN_ARG, STDIN_ARG], '1\n')
    cmd.run(ProcessMode.YES)

    assert cmd.log == ['prepared', 'planned 1', 'did 1']


def test_a_typed_value_that_fails_is_counted_and_named(monkeypatch, capsys):
    cmd = a_list_command(
        monkeypatch, [13, STDIN_ARG], '1\n', cls=AFussyListCommand)
    cmd.set_keep_going()

    assert cmd.run(ProcessMode.YES) == 1
    assert capsys.readouterr().err.startswith(
        '13: Something does not seem to exist')


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


def test_streaming_lists_each_item_without_banner(monkeypatch, capsys):
    cmd = a_command(monkeypatch, slots(STDIN_ARG), '1\n2\n')
    cmd.run(ProcessMode.YES)

    assert capsys.readouterr().out == (
        '- note 1\n'
        '- note 2\n')


def test_streaming_an_empty_input_says_nothing(monkeypatch, capsys):
    cmd = a_command(monkeypatch, slots(STDIN_ARG), '')
    cmd.run(ProcessMode.YES)

    assert capsys.readouterr().out == ''


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


# -- keep going --

def a_fussy_command(monkeypatch, stdin, keep_going=True, values=None):
    "One that refuses 13, its input on stdin unless values says not"
    arg_slots = slots(STDIN_ARG) if values is None else slots(*values)
    cmd = a_command(monkeypatch, arg_slots, stdin, cls=AFussyCommand)
    if keep_going:
        cmd.set_keep_going()
    return cmd


def test_an_item_that_fails_stops_the_run(monkeypatch):
    "The default: what is done is done, and the rest is not tried"
    cmd = a_fussy_command(monkeypatch, '1\n13\n2\n', keep_going=False)

    with pytest.raises(UnrecognisedItem):
        cmd.run(ProcessMode.YES)

    assert cmd.log == ['prepared', 'planned 1', 'did 1']


def test_keep_going_carries_on_to_the_next_item(monkeypatch):
    cmd = a_fussy_command(monkeypatch, '1\n13\n2\n')
    cmd.run(ProcessMode.YES)

    assert cmd.log == [
        'prepared', 'planned 1', 'did 1', 'planned 2', 'did 2']


def test_keep_going_survives_a_line_it_cannot_read(monkeypatch):
    "A malformed line is an item failing, not the end of the input"
    cmd = a_fussy_command(monkeypatch, '1\nnonsense\n2\n')
    cmd.run(ProcessMode.YES)

    assert cmd.log == [
        'prepared', 'planned 1', 'did 1', 'planned 2', 'did 2']


def test_keep_going_returns_how_many_failed(monkeypatch):
    cmd = a_fussy_command(monkeypatch, '1\n13\nnonsense\n2\n')

    assert cmd.run(ProcessMode.YES) == 2


def test_nothing_failing_returns_zero(monkeypatch):
    cmd = a_fussy_command(monkeypatch, '1\n2\n')

    assert cmd.run(ProcessMode.YES) == 0


def test_the_batch_path_returns_zero_too(monkeypatch):
    cmd = a_command(monkeypatch, slots(1))

    assert cmd.run(ProcessMode.YES) == 0


def test_a_failed_item_says_which_line_it_was(monkeypatch, capsys):
    cmd = a_fussy_command(monkeypatch, '13\n')
    cmd.run(ProcessMode.YES)

    assert capsys.readouterr().err.startswith(
        '13: Something does not seem to exist')


def test_the_failures_are_counted_up_at_the_end(monkeypatch, capsys):
    cmd = a_fussy_command(monkeypatch, '1\n13\n2\n')
    cmd.run(ProcessMode.YES)

    assert 'Failed on 1 of 3 items' in capsys.readouterr().err


def test_keep_going_leaves_the_batch_path_alone(monkeypatch):
    "There the plan is made before anything is written, so it stops"
    cmd = a_fussy_command(monkeypatch, '', values=(13,))

    with pytest.raises(UnrecognisedItem):
        cmd.run(ProcessMode.YES)


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
