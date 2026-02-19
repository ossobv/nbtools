from collections import namedtuple
from configparser import ConfigParser, MissingSectionHeaderError
from os import path

from .exceptions import StartupError


CONF_FILE = '~/.config/nbtools.ini'


class Config(namedtuple('Config', 'api_url api_url_base api_token')):
    """
    Load NetBox API config (url, token) from INI file.

    Example INI:

        [netbox.example.com]
        api_url = https://netbox.example.com/api
        api_token = mytoken
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
                api_token=data['api_token'])
        except KeyError as e:
            raise StartupError(
                f'api_url or api_token not found in {filename}') from e
