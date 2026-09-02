from collections import namedtuple
from configparser import ConfigParser, MissingSectionHeaderError
from os import path

from .exceptions import StartupError
from .netbox import DEFAULT_RETRIES, DEFAULT_TIMEOUT


CONF_FILE = '~/.config/nbtools.ini'

CONFIG_FIELDS = 'api_url api_url_base api_token api_retries api_timeout'


class Config(namedtuple(
        'Config', CONFIG_FIELDS,
        defaults=(DEFAULT_RETRIES, DEFAULT_TIMEOUT))):
    """
    Load NetBox API config (url, token) from INI file.

    Example INI:

        [netbox.example.com]
        api_url = https://netbox.example.com/api
        api_token = mytoken
        api_retries = 3        ; optional, 0 turns retrying off
        api_timeout = 5,60     ; optional, (connect, read) seconds
    """
    @classmethod
    def from_defaults(cls):
        return cls.from_ini(path.expanduser(CONF_FILE))

    @classmethod
    def from_ini(cls, filename):
        ini = ConfigParser(
            delimiters=('=',), allow_no_value=True,
            inline_comment_prefixes=('#', ';'))
        try:
            ini.read(filename)
        except MissingSectionHeaderError as e:
            raise StartupError(f'{e} in in {filename}') from e

        if len(ini.sections()) != 1:
            raise StartupError(f'expected exactly one section in {filename}')

        the_section = ini.sections()[0]
        data = dict(ini.items(the_section))
        try:
            # api_url, with "/api": "https://netbox.example.com/api"
            assert data['api_url'].endswith('/api'), data['api_url']
            return cls(
                api_url=data['api_url'],
                api_url_base=data['api_url'][0:-4],  # pynetbox wants this
                api_token=data['api_token'],
                api_retries=_parse_retries(
                    data.get('api_retries'), filename),
                api_timeout=_parse_timeout(
                    data.get('api_timeout'), filename))
        except KeyError as e:
            raise StartupError(
                f'api_url or api_token not found in {filename}') from e


def _parse_retries(text, filename):
    """
    How often a read may be tried again; 0 turns retrying off
    """
    if text is None:
        return DEFAULT_RETRIES

    try:
        retries = int(text)
        if retries < 0:
            raise ValueError(text)
    except ValueError as e:
        raise StartupError(
            f'api_retries must be a whole number, 0 or more, '
            f'in {filename}') from e

    return retries


def _parse_timeout(text, filename):
    """
    The (connect, read) timeouts, as "5,60" or one number for both

    The read half should not be too low! nblint reads whole tables with
    limit=0, and a slow success has to stay a success, or the timeout
    manufactures the retries it was meant to catch.
    """
    if text is None:
        return DEFAULT_TIMEOUT

    parts = [part.strip() for part in text.split(',')]
    if len(parts) == 1:
        parts = [parts[0], parts[0]]

    try:
        if len(parts) != 2:
            raise ValueError(text)
        connect, read = (float(part) for part in parts)
        if connect <= 0 or read <= 0:
            raise ValueError(text)
    except ValueError as e:
        raise StartupError(
            f'api_timeout must be "SECONDS" or "CONNECT,READ", '
            f'both above zero, in {filename}') from e

    return (connect, read)
