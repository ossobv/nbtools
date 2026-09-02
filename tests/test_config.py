"""
The INI, and the two optional keys the 408 work added to it.

api_retries and api_timeout describe the install rather than the
invocation, so they live here rather than on the command line. Both
are optional: the file that exists today, with only a URL and a token
in it, has to keep working and get the defaults.
"""
import pytest

from nbtools.config import Config
from nbtools.exceptions import StartupError
from nbtools.netbox import DEFAULT_RETRIES, DEFAULT_TIMEOUT


MINIMAL = """\
[netbox.example.com]
api_url = https://netbox.example.com/api
api_token = mytoken
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
