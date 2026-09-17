"""
The --help of both tools, and of their commands.

The tool's --help lists every command, so it gets the first sentence
of each; the command's own --help is where the rest of it goes.
"""
import sys

import pytest

from nbtools import lint, sync
from nbtools.command import Command
from nbtools.lintcmd import COMMANDS as LINT_COMMANDS
from nbtools.synccmd import COMMANDS as SYNC_COMMANDS


TOOLS = [
    ('nblint', lint.main, LINT_COMMANDS),
    ('nbsync', sync.main, SYNC_COMMANDS),
]

EVERY_COMMAND = [
    pytest.param(prog, main, cmdcls, id=f'{prog}-{cmdcls.name}')
    for prog, main, commands in TOOLS
    for cmdcls in commands]


def help_of(monkeypatch, capsys, main, argv):
    "What main() prints for argv, its line wrapping undone"
    # Wide enough that argparse wraps nothing, so no hyphenated word
    # gets split across lines.
    monkeypatch.setenv('COLUMNS', '10000')
    monkeypatch.setattr(sys, 'argv', argv)

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 0
    return ' '.join(capsys.readouterr().out.split())


def a_command(text):
    return type('ACommand', (Command,), {'name': 'a', 'help': text})


def test_the_summary_is_the_first_sentence():
    assert a_command(
        'Find things. They are wrong. Really.').summary() == 'Find things.'


def test_the_summary_of_one_sentence_is_all_of_it():
    assert a_command('Find things.').summary() == 'Find things.'
    assert a_command('Find things: ^x$').summary() == 'Find things: ^x$'


def test_a_dot_inside_a_word_does_not_end_the_sentence():
    assert a_command(
        'Find swp1.1234 on leaf1.example. And so on.').summary() == (
            'Find swp1.1234 on leaf1.example.')


def test_the_summary_ends_at_the_paragraph():
    assert a_command(
        'Find things\n\nThey are wrong.').summary() == 'Find things'


def test_an_abbreviation_does_not_end_the_sentence():
    assert a_command(
        'Set a type, e.g. bridge. And so on.').summary() == (
            'Set a type, e.g. bridge.')


@pytest.mark.parametrize(('prog', 'main', 'commands'), TOOLS,
                         ids=[prog for prog, _main, _cmds in TOOLS])
def test_the_tool_help_lists_the_summaries(
        monkeypatch, capsys, prog, main, commands):
    out = help_of(monkeypatch, capsys, main, [prog, '--help'])

    for cmdcls in commands:
        assert f'{cmdcls.name} {cmdcls.summary()}' in out
        if cmdcls.summary() != cmdcls.help:
            assert ' '.join(cmdcls.help.split()) not in out


@pytest.mark.parametrize(('prog', 'main', 'cmdcls'), EVERY_COMMAND)
def test_the_command_help_holds_the_whole_description(
        monkeypatch, capsys, prog, main, cmdcls):
    out = help_of(monkeypatch, capsys, main, [prog, cmdcls.name, '--help'])

    assert out.startswith(f'usage: {prog} {cmdcls.name} ')
    assert ' '.join(cmdcls.help.split()) in out


@pytest.mark.parametrize(('prog', 'main', 'commands'), TOOLS,
                         ids=[prog for prog, _main, _cmds in TOOLS])
def test_no_two_commands_share_a_summary(prog, main, commands):
    summaries = [cmdcls.summary() for cmdcls in commands]

    assert len(set(summaries)) == len(summaries)


@pytest.mark.parametrize(('prog', 'main', 'cmdcls'), EVERY_COMMAND)
def test_the_description_fits_79_columns(prog, main, cmdcls):
    # Wrapped paragraphs fit whatever the terminal; an example is
    # printed as written, so it has to fit to begin with.
    for line in cmdcls.help.split('\n'):
        if line.startswith(' '):
            assert len(line) <= 79, line


def examples_in(monkeypatch, capsys, main, argv):
    "The (tool, COMMAND) of every example command line in the help"
    monkeypatch.setenv('COLUMNS', '80')
    monkeypatch.setattr(sys, 'argv', argv)

    with pytest.raises(SystemExit):
        main()

    names = {prog for prog, _main, _commands in TOOLS}
    for line in capsys.readouterr().out.split('\n'):
        words = line.split()
        if not line.startswith(' ') or not words or words[0] not in names:
            continue

        command = next(word for word in words[1:] if word[0] != '-')
        yield words[0], command


def test_the_examples_are_found(monkeypatch, capsys):
    assert list(examples_in(
        monkeypatch, capsys, lint.main,
        ['nblint', 'duplicate-macs', '--help'])) == [
            ('nblint', 'duplicate-macs'), ('nbsync', 'unset-interface-mac')]


@pytest.mark.parametrize('argv', [
    [prog, *name] for prog, _main, commands in TOOLS
    for name in [('--help',)] + [(cmdcls.name, '--help')
                                 for cmdcls in commands]],
    ids=(lambda argv: ' '.join(argv)))
def test_the_examples_name_real_commands(monkeypatch, capsys, argv):
    known = {
        prog: {cmdcls.name for cmdcls in commands}
        for prog, _main, commands in TOOLS}
    main = {prog: main for prog, main, _commands in TOOLS}[argv[0]]

    for prog, command in examples_in(monkeypatch, capsys, main, argv):
        assert command in known[prog], (prog, command)
