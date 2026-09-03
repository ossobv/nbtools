"""
The --status flag itself: parsing, and what a run without it reports.

The command tests go in through set_statuses(); this is the argparse
half, plus the one behaviour that is easier to state here than
through a command -- that the default is "everything but reserved"
rather than a list of the statuses we happen to know about.
"""
from argparse import ArgumentParser

import pytest

from nbtools.lintcmd.statusarg import StatusArgument

from ..nbstub import NS


def a_status_argument():
    return StatusArgument(
        'prefixes', ('container', 'reserved', 'deprecated', 'active'),
        skipped_by_default=('reserved',),
        reason='a reserved prefix is empty by design')


def parse(*argv):
    "The statuses this command line asks for, flattened"
    status_arg = a_status_argument()
    parser = ArgumentParser(prog='empty-prefixes')
    status_arg.add_argument(parser)

    return status_arg.from_args(parser.parse_args(argv))


def a_record(status):
    return NS(id=1, status=NS(value=status, label=status.title()))


# -- the argparse half --

def test_no_status_is_an_empty_list():
    assert parse() == []


def test_one_status():
    assert parse('--status', 'active') == ['active']


def test_the_equals_spelling_reads_the_same():
    assert parse('--status=active') == ['active']


def test_comma_separated_statuses_come_out_as_several():
    assert parse('--status=container,active') == ['container', 'active']


def test_whitespace_around_a_comma_is_allowed():
    assert parse('--status=container, active') == ['container', 'active']


def test_the_flag_is_repeatable():
    assert parse('--status=container', '--status=active') == [
        'container', 'active']


def test_repeats_and_commas_mix():
    assert parse('--status=container,active', '--status=reserved') == [
        'container', 'active', 'reserved']


def test_all_is_a_value_like_any_other():
    assert parse('--status=all') == ['all']


def test_an_unknown_status_is_a_usage_error(capsys):
    with pytest.raises(SystemExit):
        parse('--status=retired')

    assert "'retired': expected all or one of" in capsys.readouterr().err


def test_one_bad_status_fails_the_whole_value(capsys):
    "Half a filter would report the wrong thing rather than nothing"
    with pytest.raises(SystemExit):
        parse('--status=active,retired')

    assert "'retired': expected" in capsys.readouterr().err


def test_the_help_names_the_choices_and_the_default():
    help_text = a_status_argument().help()

    assert 'One of: container, reserved, deprecated, active.' in help_text
    assert 'Default: container,deprecated,active' in help_text
    assert 'reserved is left out, a reserved prefix is empty by design' \
        in help_text
    assert 'Pass "all" for every status, reserved included.' in help_text


# -- what the flag resolves to --

def test_the_default_reports_everything_but_the_skipped():
    statuses = a_status_argument().filter_for()

    assert statuses.allows(a_record('active'))
    assert statuses.allows(a_record('container'))
    assert not statuses.allows(a_record('reserved'))


def test_an_empty_list_is_the_default_too():
    assert not a_status_argument().filter_for([]).allows(a_record('reserved'))


def test_a_named_status_is_the_only_one_left_in():
    statuses = a_status_argument().filter_for(['container'])

    assert statuses.allows(a_record('container'))
    assert not statuses.allows(a_record('active'))


def test_naming_reserved_is_all_it_takes_to_get_it():
    "The allowlist has no default to un-skip first"
    assert a_status_argument().filter_for(
        ['reserved']).allows(a_record('reserved'))


def test_all_among_the_values_wins():
    statuses = a_status_argument().filter_for(['container', 'all'])

    assert statuses.allows(a_record('reserved'))
    assert statuses.allows(a_record('active'))


def test_a_status_we_have_never_heard_of_is_still_reported_by_default():
    """
    A NetBox can be configured with choices of its own.

    That is why the default is the exclude kind rather than the list
    of statuses above: a run that asked for nothing in particular
    should not quietly drop a record because of a word this code does
    not know.
    """
    status_arg = a_status_argument()

    assert status_arg.filter_for().allows(a_record('quarantined'))
    assert status_arg.filter_for(['all']).allows(a_record('quarantined'))
    assert not status_arg.filter_for(['active']).allows(
        a_record('quarantined'))


def test_a_record_with_no_status_at_all_survives_the_default():
    "status_name() spells it '-'; the default excludes reserved only"
    assert a_status_argument().filter_for().allows(NS(id=1))
