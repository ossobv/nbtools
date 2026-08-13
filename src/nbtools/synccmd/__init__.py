from .clone_if import CloneInterfaceCommand
from .migr_if import MigrateInterfaceCommand
from .set_if_ip import SetInterfaceIpByMacCommand, SetInterfaceIpCommand
from .swap_cables import SwapCableCommand
from .unset_if_mac import UnsetInterfaceMacCommand
from .zap_if import ZapInterfaceCommand


# The subcommands nbsync offers, in --help order. Registration is kept
# explicit on purpose: no import scanning, so the list stays greppable.
COMMANDS = (
    # Interface commands
    CloneInterfaceCommand,
    MigrateInterfaceCommand,
    SetInterfaceIpCommand,
    SetInterfaceIpByMacCommand,
    UnsetInterfaceMacCommand,
    ZapInterfaceCommand,
    # Other commands
    SwapCableCommand,
)

COMMANDS_BY_NAME = {cmdcls.name: cmdcls for cmdcls in COMMANDS}
