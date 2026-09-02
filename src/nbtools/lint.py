#!/usr/bin/env python3
from argparse import ArgumentParser
import logging
import sys

from .config import CONF_FILE, Config
from .exceptions import StartupError, StateError
from .lintcmd import COMMANDS, COMMANDS_BY_NAME
from .netbox import connect, translated_errors


def main() -> None:
    parser = ArgumentParser(
        prog='nblint',
        description=(
            'Reporter for NetBox source of truth data. Finds records that '
            'look wrong and prints them. Changes nothing: that is what '
            'nbsync is for.'),
        epilog=(
            'Without a COMMAND it runs them all. Exits 0 when everything is '
            'clean and 1 when there are findings, so it can be run from '
            'cron. Feed the findings of one COMMAND to nbsync with '
            '--porcelain, e.g. "nblint --porcelain duplicate-macs | xargs '
            'nbsync unset-interface-mac :".'))
    parser.add_argument(
        '-c', '--config', metavar='INIFILE',
        help=f'configuration INI location (default: {CONF_FILE})')
    parser.add_argument('--debug', action='store_true', help=(
        'Enable debug output.'))
    parser.add_argument('--porcelain', action='store_true', help=(
        'Print one value per line and no banners, for feeding into '
        'nbsync. Needs a COMMAND: see the example below.'))

    command = parser.add_subparsers(dest='command')
    for cmdcls in COMMANDS:
        cmdcls.add_arguments(
            command.add_parser(cmdcls.name, help=cmdcls.help))

    args = parser.parse_args()

    # Each command emits its own kind of value, so a --porcelain run of
    # all of them would be a stream of things the reader cannot tell
    # apart. Name the one you want to pipe.
    if args.porcelain and args.command is None:
        parser.error('--porcelain needs a COMMAND to print the values of')

    # Setup logging.
    logging.basicConfig(
        level=(logging.DEBUG if args.debug else logging.INFO),
        format='%(asctime)s %(message)s',
        stream=sys.stdout,
        datefmt='%Y-%m-%d %H:%M:%S')

    # Load config for API URL/tokens.
    try:
        if args.config is None:
            config = Config.from_defaults()
        else:
            config = Config.from_ini(args.config)
    except StartupError as e:
        parser.error(str(e))

    # Connect netbox API.
    nbapi = connect(config)

    # No COMMAND given means all of them.
    if args.command is None:
        cmds = [cmdcls(nbapi) for cmdcls in COMMANDS]
    else:
        cmds = [COMMANDS_BY_NAME[args.command].from_args(nbapi, args)]

    if args.porcelain:
        for cmd in cmds:
            cmd.set_porcelain()

    # Run commands.
    findings = 0
    try:
        with translated_errors():
            for cmd in cmds:
                findings += cmd.run()
    except StateError as e:
        print(
            (f'{parser.prog}: Failure while checking: '
             f'{e.description}: {e}'),
            file=sys.stderr)
        if e.hint and not args.porcelain:
            print(f'{parser.prog}: {e.hint}', file=sys.stderr)
        sys.exit(3)

    sys.exit(1 if findings else 0)


if __name__ == '__main__':
    main()
