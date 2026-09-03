from .dup_macs import DuplicateMacsCommand
from .empty_prefixes import EmptyPrefixesCommand
from .unassigned_ips import UnassignedIpsCommand


# The subcommands nblint offers, in --help order. Registration is kept
# explicit on purpose: no import scanning, so the list stays greppable.
COMMANDS = (
    UnassignedIpsCommand,
    EmptyPrefixesCommand,
    DuplicateMacsCommand,
)

COMMANDS_BY_NAME = {cmdcls.name: cmdcls for cmdcls in COMMANDS}
