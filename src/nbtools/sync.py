#!/usr/bin/env python3
from argparse import ArgumentParser
import logging
import sys

import pynetbox

from .cmd import COMMANDS, COMMANDS_BY_NAME
from .command import ProcessMode
from .config import CONF_FILE, Config
from .exceptions import StartupError, StateError
from .recorder import NetboxRecorder


def main() -> None:
    parser = ArgumentParser(
        prog='nbsync',
        description=(
            'Editor for NetBox source of truth data. Automates common tasks '
            'like moving cables between devices/interfaces, duplicating '
            'interfaces, updating IPs.'),
        epilog=(
            'Each subcommand has its own options; '
            'see "nbsync SUBCOMMAND --help".'))
    parser.add_argument(
        '-c', '--config', metavar='INIFILE',
        help=f'configuration INI location (default: {CONF_FILE})')
    parser.add_argument('--batch', action='store_true', help=(
        'Do it without asking for input. Reduce visual clutter.'))
    parser.add_argument('--debug', action='store_true', help=(
        'Enable debug output.'))
    parser.add_argument('--record', action='store', help=(
        'Record API calls into specified file.'))

    command = parser.add_subparsers(dest='command')
    for cmdcls in COMMANDS:
        cmdcls.add_arguments(
            command.add_parser(cmdcls.name, help=cmdcls.help))

    args = parser.parse_args()

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

    # Any command?
    if args.command is None:
        parser.print_usage()
        sys.exit(1)

    # Connect API.
    nbapi = pynetbox.api(config.api_url_base, token=config.api_token)

    # Start recording all netbox API calls, if requested.
    if args.record:
        recorder = NetboxRecorder.from_patched_nbapi(nbapi)

    # Run command.
    try:
        cmd = COMMANDS_BY_NAME[args.command].from_args(nbapi, args)
        if args.batch:
            cmd.set_quiet()
            cmd.run(ProcessMode.YES)
        else:
            cmd.run(ProcessMode.INTERACTIVE)
    except StateError as e:
        print(
            (f'{parser.prog}: Failure while processing: '
             f'{e.description}: {e}'),
            file=sys.stderr)
        if e.hint:
            print(f'{parser.prog}: {e.hint}', file=sys.stderr)
        sys.exit(3)
    finally:
        # Save recording.
        if args.record:
            recorder.save(args.record)


if __name__ == '__main__':
    main()
