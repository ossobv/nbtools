#!/usr/bin/env python3
from argparse import ArgumentParser
import logging
import sys

import pynetbox

from .command import ProcessMode
from .config import CONF_FILE, Config
from .exceptions import StartupError, StateError
from .recorder import NetboxRecorder

# Interface commands
from .cmd.clone_if import CloneInterfaceCommand
from .cmd.migr_if import MigrateInterfaceCommand
from .cmd.zap_if import ZapInterfaceCommand

# Other commands
from .cmd.swap_cables import SwapCableCommand


def dev_iface(dev_iface_str):
    "Takes 'leaf1:eth0' returns ('leaf1', 'eth0')"
    try:
        dev, iface = dev_iface_str.split(':')
    except ValueError as e:
        raise ValueError('argument must be DEV:IFACE') from e
    return dev, iface


def run_command(command, nbapi, args):
    assert command, command

    if command == 'clone-interface':
        cmd = CloneInterfaceCommand(nbapi)
        cmd.set_source_interface(args.source[0], args.source[1])
        cmd.set_target_interface(args.target[0], args.target[1])
        cmd.run(ProcessMode.INTERACTIVE)

    elif command == 'migrate-interface':
        cmd = MigrateInterfaceCommand(nbapi)
        cmd.set_source_interface(args.source[0], args.source[1])
        cmd.set_target_interface(args.target[0], args.target[1])
        cmd.run(ProcessMode.INTERACTIVE)

    elif command == 'zap-interface':
        cmd = ZapInterfaceCommand(nbapi)
        cmd.set_target_interface(args.target[0], args.target[1])
        cmd.run(ProcessMode.INTERACTIVE)

    elif command == 'swap-cables':
        cmd = SwapCableCommand(nbapi)
        cmd.set_a_interface(args.iface1[0], args.iface1[1])
        cmd.set_b_interface(args.iface2[0], args.iface2[1])
        cmd.run(ProcessMode.INTERACTIVE)

    else:
        raise NotImplementedError('unknown command: {command}')


def main() -> None:
    parser = ArgumentParser(prog='nbsync', description='FIXME nbtools utils')
    parser.add_argument(
        '-c', '--config', metavar='INIFILE',
        help=f'configuration INI location (default: {CONF_FILE})')
    parser.add_argument('--debug', action='store_true', help=(
        'Enable debug output.'))
    parser.add_argument('--record', action='store', help=(
        'Record API calls into specified file.'))

    command = parser.add_subparsers(dest='command')

    # clone-interface command
    clone_if = command.add_parser('clone-interface', help=(
        'Clone interface with subinterfaces from source to target. '
        'Useful when having a machine connected to multiple interfaces. '
        'It will duplicate the virtual child interfaces. '
        'It will copy the IPv4 addresses to the appropriate child (vlan) '
        'interfaces. '
        'It sets role=anycast on the IPs so they can be assigned to multiple '
        'interfaces.'))
    clone_if.add_argument('source', type=dev_iface, help=(
        'Source device and interface (e.g. leaf1:swp19)'))
    clone_if.add_argument('target', type=dev_iface, help=(
        'Target device and interface (e.g. leaf2:swp19)'))

    # migrate-interface command
    migr_if = command.add_parser('migrate-interface', help=(
        'Migrate properties of an interface -- subinterfaces, IPs and cables '
        '-- from source to target. '
        'Target should start out empty. Source will be zapped. '
        'Useful when moving a cable from one switch to another.'))
    migr_if.add_argument('source', type=dev_iface, help=(
        'Source device and interface (e.g. leaf1:swp19)'))
    migr_if.add_argument('target', type=dev_iface, help=(
        'Target device and interface (e.g. leaf2:swp8'))

    # zap-interface command
    zap_if = command.add_parser('zap-interface', help=(
        'Zap (clean/wipe) properties from an interface. '
        'Keeps the interface, but wipes tags, descriptions, '
        'subinterfaces and assigned IPs. '
        'Useful to wipe target before calling migrate-interface.'))
    zap_if.add_argument('target', type=dev_iface, help=(
        'Target device and interface (e.g. leaf2:swp8'))

    # swap-cables command
    swap_cables = command.add_parser('swap-cables', help=(
        'Swap two connected cables. Changes A1<->B1 and A2<->B2 to '
        'A1<->B2 and A2<->B1.'))
    swap_cables.add_argument('iface1', type=dev_iface, help=(
        'One connected device and interface (e.g. pve1:enmlx1)'))
    swap_cables.add_argument('iface2', type=dev_iface, help=(
        'Other connected device and interface (e.g. pve1:enmlx0'))

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
        run_command(args.command, nbapi, args)
    except StateError as e:
        print(
            (f'{parser.prog}: Failure while processing: '
             f'{e.__doc__}: {e}'),
            file=sys.stderr)
        sys.exit(3)
    finally:
        # Save recording.
        if args.record:
            recorder.save(args.record)


if __name__ == '__main__':
    main()
