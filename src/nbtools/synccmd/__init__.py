from .clone_if import CloneInterfaceCommand
from .migr_if import MigrateInterfaceCommand
from .set_if_ip import SetInterfaceIpByMacCommand, SetInterfaceIpCommand
from .swap_cables import SwapCableCommand
from .zap_if import ZapInterfaceCommand
from .zap_macs import ZapMacAddressCommand


# The subcommands nbsync offers, in --help order. Registration is kept
# explicit on purpose: no import scanning, so the list stays greppable.
COMMANDS = (
    # Interface commands
    CloneInterfaceCommand,
    MigrateInterfaceCommand,
    SetInterfaceIpCommand,
    SetInterfaceIpByMacCommand,
    ZapInterfaceCommand,
    # Other commands
    SwapCableCommand,
    ZapMacAddressCommand,
)

COMMANDS_BY_NAME = {cmdcls.name: cmdcls for cmdcls in COMMANDS}
