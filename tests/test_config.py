"""
The INI, the two optional keys the 408 work added to it, and picking a
context out of it.

api_retries and api_timeout describe the install rather than the
invocation, so they live here rather than on the command line. Both
are optional: the file that exists today, with only a URL and a token
in it, has to keep working and get the defaults.
"""
import sys

import pytest

from nbtools import lint, sync
from nbtools.config import Config
from nbtools.exceptions import StartupError
from nbtools.netbox import DEFAULT_RETRIES, DEFAULT_TIMEOUT


MINIMAL = """\
[netbox.example.com]
api_url = https://netbox.example.com/api
api_token = mytoken
"""


TWO_CONTEXTS = MINIMAL + """\
api_retries = 1

[netbox.test]
api_url = https://netbox.test/api
api_token = testtoken
"""


def an_ini(tmp_path, text):
    filename = tmp_path / 'nbtools.ini'
    filename.write_text(text)
    return str(filename)


def a_config(tmp_path, *extra_lines):
    "The minimal file, plus these lines in the same section"
    lines = ''.join(f'{line}\n' for line in extra_lines)

    return Config.from_ini(an_ini(tmp_path, MINIMAL + lines))


def test_the_file_that_exists_today_still_loads(tmp_path):
    config = a_config(tmp_path)

    assert config.api_url == 'https://netbox.example.com/api'
    assert config.api_url_base == 'https://netbox.example.com'
    assert config.api_token == 'mytoken'
    assert config.api_retries == DEFAULT_RETRIES
    assert config.api_timeout == DEFAULT_TIMEOUT


def test_both_can_be_set(tmp_path):
    config = a_config(tmp_path, 'api_retries = 5', 'api_timeout = 2,30')

    assert config.api_retries == 5
    assert config.api_timeout == (2.0, 30.0)


def test_retries_can_be_none_at_all(tmp_path):
    "0 turns retrying off, which is a setting and not an error"
    assert a_config(tmp_path, 'api_retries = 0').api_retries == 0


def test_one_timeout_covers_both_halves(tmp_path):
    assert a_config(tmp_path, 'api_timeout = 30').api_timeout == (30.0, 30.0)


def test_a_comment_after_the_value_is_not_the_value(tmp_path):
    "The reader is built with inline comments on; check they still are"
    config = a_config(tmp_path, 'api_retries = 2  ; two is plenty')

    assert config.api_retries == 2


@pytest.mark.parametrize('line', (
    'api_retries = lots',
    'api_retries = -1',
    'api_retries = 1.5',
))
def test_a_retry_count_that_is_not_one(tmp_path, line):
    with pytest.raises(StartupError, match='api_retries'):
        a_config(tmp_path, line)


@pytest.mark.parametrize('line', (
    'api_timeout = soon',
    'api_timeout = 0',
    'api_timeout = -1,30',
    'api_timeout = 1,2,3',
))
def test_a_timeout_that_is_not_one(tmp_path, line):
    with pytest.raises(StartupError, match='api_timeout'):
        a_config(tmp_path, line)


def test_the_defaults_are_a_pair_of_seconds():
    "Connect and read, in that order, as requests wants them"
    connect, read = DEFAULT_TIMEOUT

    assert 0 < connect < read


def test_the_one_context_needs_no_naming(tmp_path):
    config = Config.from_ini(an_ini(tmp_path, MINIMAL))

    assert config.api_token == 'mytoken'


def test_the_one_context_can_still_be_named(tmp_path):
    config = Config.from_ini(
        an_ini(tmp_path, MINIMAL), 'netbox.example.com')

    assert config.api_token == 'mytoken'


@pytest.mark.parametrize('context,token,retries', (
    ('netbox.example.com', 'mytoken', 1),
    ('netbox.test', 'testtoken', DEFAULT_RETRIES),
))
def test_a_context_is_picked_by_name(tmp_path, context, token, retries):
    "And only its own keys come along"
    config = Config.from_ini(an_ini(tmp_path, TWO_CONTEXTS), context)

    assert config.api_token == token
    assert config.api_retries == retries


def test_several_contexts_are_not_guessed_between(tmp_path):
    "The error names the choices"
    with pytest.raises(StartupError, match=(
            r'--context: netbox\.example\.com, netbox\.test$')):
        Config.from_ini(an_ini(tmp_path, TWO_CONTEXTS))


@pytest.mark.parametrize('text', (MINIMAL, TWO_CONTEXTS))
def test_a_context_that_is_not_there(tmp_path, text):
    with pytest.raises(StartupError, match="context 'netbox.prod'"):
        Config.from_ini(an_ini(tmp_path, text), 'netbox.prod')


def test_a_file_that_is_not_there(tmp_path):
    with pytest.raises(StartupError, match='cannot read'):
        Config.from_ini(str(tmp_path / 'nonexistent.ini'))


def test_a_file_without_contexts(tmp_path):
    with pytest.raises(StartupError, match='no context'):
        Config.from_ini(an_ini(tmp_path, ''))


class Connected(Exception):
    "Raised in place of connecting, carrying the config it was given"


@pytest.mark.parametrize('main,command', (
    (lint.main, []),
    # nbsync wants a command before it connects; it never gets to run.
    (sync.main, ['zap-interface', 'leaf1:swp1']),
))
@pytest.mark.parametrize('option', ('-C', '--context'))
def test_the_tools_pass_the_context_on(
        tmp_path, monkeypatch, main, command, option):
    def connect(config, tool):
        raise Connected(config)

    monkeypatch.setattr(sys.modules[main.__module__], 'connect', connect)
    monkeypatch.setattr(sys, 'argv', [
        'nbtool', '-c', an_ini(tmp_path, TWO_CONTEXTS),
        option, 'netbox.test', *command])

    with pytest.raises(Connected) as exc:
        main()

    assert exc.value.args[0].api_token == 'testtoken'


@pytest.mark.parametrize('main', (lint.main, sync.main))
def test_the_tools_refuse_to_guess(tmp_path, monkeypatch, capsys, main):
    monkeypatch.setattr(sys, 'argv', [
        'nbtool', '-c', an_ini(tmp_path, TWO_CONTEXTS)])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2
    assert 'pick one with --context' in capsys.readouterr().err
