#!/usr/bin/env python3
from argparse import ArgumentParser
import logging
import sys

from .cli import ParagraphHelpFormatter, add_commands
from .command import ProcessMode
from .config import CONF_FILE, Config
from .exceptions import StartupError, StateError
from .netbox import connect, translated_errors
from .recorder import NetboxRecorder
from .synccmd import COMMANDS, COMMANDS_BY_NAME


def main() -> None:
    parser = ArgumentParser(
        prog='nbsync',
        description=(
            'Editor for NetBox source of truth data. Automates common tasks '
            'like moving cables between devices/interfaces, duplicating '
            'interfaces, updating IPs.'),
        epilog=(
            'Lists the work it is about to do and asks before doing it; '
            '--batch does it without asking. An argument given as "-" is '
            'read from stdin instead, one item per line, each done as it '
            'arrives -- which needs --batch, stdin being taken. That is '
            'how the findings of nblint --porcelain get fixed:\n'
            '\n'
            '  nblint --porcelain interface-types --limit=bridge |\n'
            '    nbsync --batch set-interface-type bridge -\n'
            '\n'
            'Each COMMAND has its own options and a fuller description; '
            'see "nbsync COMMAND --help".'),
        formatter_class=ParagraphHelpFormatter)
    parser.add_argument(
        '-c', '--config', metavar='INIFILE',
        help=f'configuration INI location (default: {CONF_FILE})')
    parser.add_argument(
        '-C', '--context', metavar='NAME',
        help=(
            'the INI [section] to use; needed when the file has more '
            'than one'))
    parser.add_argument('--batch', action='store_true', help=(
        'Do it without asking for input. Reduce visual clutter.'))
    parser.add_argument('--keep-going', action='store_true', help=(
        'Report an item that fails and carry on with the next one, '
        'instead of stopping. Only items read from stdin come one at '
        'a time, so this does nothing without them. Exits nonzero if '
        'anything failed.'))
    parser.add_argument('--debug', action='store_true', help=(
        'Enable debug output.'))
    parser.add_argument('--record', action='store', help=(
        'Record API calls into specified file.'))

    add_commands(parser, COMMANDS, help='the change to make')

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
            config = Config.from_defaults(args.context)
        else:
            config = Config.from_ini(args.config, args.context)
    except StartupError as e:
        parser.error(str(e))

    # Any command?
    if args.command is None:
        parser.print_usage()
        sys.exit(1)

    # Connect netbox API.
    nbapi = connect(config, parser.prog)

    # Start recording all netbox API calls, if requested.
    if args.record:
        recorder = NetboxRecorder.from_patched_nbapi(nbapi)

    # Run command.
    try:
        with translated_errors():
            cmd = COMMANDS_BY_NAME[args.command].from_args(nbapi, args)
            if args.keep_going:
                cmd.set_keep_going()
            if args.batch:
                cmd.set_quiet()
                failed = cmd.run(ProcessMode.YES)
            else:
                failed = cmd.run(ProcessMode.INTERACTIVE)
    except StateError as e:
        print(
            (f'{parser.prog}: Failure while processing: '
             f'{e.description}: {e}'),
            file=sys.stderr)
        if e.hint and not args.batch:
            print(f'{parser.prog}: {e.hint}', file=sys.stderr)
        sys.exit(3)
    finally:
        # Save recording.
        if args.record:
            recorder.save(args.record)

    # Nothing raised, but --keep-going may have swallowed something.
    if failed:
        sys.exit(3)


if __name__ == '__main__':
    main()
