"""
The shared CLI surface: paragraph help layout and bash completion.

The completion script is run in a real bash, fed COMP_WORDS the way
bash splits a command line -- '=' being a word of its own.
"""
import shutil
import subprocess
import sys

import pytest

from nbtools import lint, sync
from nbtools.cli import ParagraphHelpFormatter
from nbtools.lintcmd import COMMANDS as LINT_COMMANDS
from nbtools.synccmd import COMMANDS as SYNC_COMMANDS


def fill(text, width=40, indent=''):
    return ParagraphHelpFormatter('prog')._fill_text(text, width, indent)


def test_paragraphs_are_wrapped_apart():
    text = (
        'One two three four five six seven eight nine ten.\n'
        '\n'
        'Eleven.')

    assert fill(text, width=20) == (
        'One two three four\n'
        'five six seven eight\n'
        'nine ten.\n'
        '\n'
        'Eleven.')


def test_an_indented_paragraph_is_kept_as_written():
    text = (
        'Example:\n'
        '\n'
        '  nblint --porcelain interface-types --limit=bridge |\n'
        '    nbsync --batch set-interface-type bridge -\n'
        '\n'
        'Done.')

    assert fill(text, width=20, indent='  ') == (
        '  Example:\n'
        '\n'
        '    nblint --porcelain interface-types --limit=bridge |\n'
        '      nbsync --batch set-interface-type bridge -\n'
        '\n'
        '  Done.')


def test_a_hyphenated_word_is_not_split():
    assert fill('aaaa unattached-cables', width=20) == (
        'aaaa\nunattached-cables')


def script_of(monkeypatch, capsys, main, prog):
    monkeypatch.setattr(sys, 'argv', [prog, 'completion', 'bash'])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 0
    return capsys.readouterr().out


def complete(script, prog, line):
    """
    What bash offers for the last word of line

    line is split on spaces the way bash would have split it; a line
    ending in a space completes an empty word.
    """
    words = line.split(' ')
    driver = (
        f'{script}\n'
        f'COMP_WORDS=("$@")\n'
        f'COMP_CWORD=$((${{#COMP_WORDS[@]}} - 1))\n'
        f'_{prog}\n'
        f'printf "%s\\n" "${{COMPREPLY[@]}}"\n')

    out = subprocess.run(
        ['bash', '--norc', '-c', driver, 'bash', *words],
        capture_output=True, text=True, check=True).stdout

    return [word for word in out.split('\n') if word]


needs_bash = pytest.mark.skipif(
    shutil.which('bash') is None, reason='no bash to run the script in')


@needs_bash
@pytest.mark.parametrize(('prog', 'main', 'commands'), [
    ('nblint', lint.main, LINT_COMMANDS),
    ('nbsync', sync.main, SYNC_COMMANDS),
])
def test_every_command_completes(monkeypatch, capsys, prog, main, commands):
    script = script_of(monkeypatch, capsys, main, prog)

    assert complete(script, prog, f'{prog} ') == (
        [cmdcls.name for cmdcls in commands] + ['completion'])


@needs_bash
@pytest.mark.parametrize(('line', 'expected'), [
    ('nblint empty', ['empty-prefixes']),
    ('nblint dup', ['duplicate-prefixes', 'duplicate-ips', 'duplicate-macs']),
    ('nblint --porcelain unatt', [
        'unattached-cables', 'unattached-interfaces']),
    ('nblint -c x.ini -C ctx empty', ['empty-prefixes']),
    ('nblint --config = x.ini empty', ['empty-prefixes']),
    ('nblint --config x.ini --context = ctx empty', ['empty-prefixes']),
    ('nblint comp', ['completion']),
    ('nblint completion ', ['bash']),
    # After a COMMAND, and in the value of an option, there is nothing
    # to offer: bash falls back to file names.
    ('nblint empty-prefixes ', []),
    ('nblint empty-prefixes --role=x dup', []),
    ('nblint completion bash ', []),
    ('nblint -c ', []),
    ('nblint -c emp', []),
    ('nblint --config = emp', []),
    ('nblint --', []),
])
def test_completion(monkeypatch, capsys, line, expected):
    script = script_of(monkeypatch, capsys, lint.main, 'nblint')

    assert complete(script, 'nblint', line) == expected


@needs_bash
def test_nbsync_skips_the_value_of_record(monkeypatch, capsys):
    script = script_of(monkeypatch, capsys, sync.main, 'nbsync')

    assert complete(script, 'nbsync', 'nbsync --record swap') == []
    assert complete(script, 'nbsync', 'nbsync --record x.json swap') == [
        'swap-cables']
