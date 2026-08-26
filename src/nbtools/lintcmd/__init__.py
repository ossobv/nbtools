from .dev_bmcs import DeviceBmcsCommand
from .dup_in_vrfs import DuplicateIpsCommand, DuplicatePrefixesCommand
from .cables import UnattachedCablesCommand
from .dup_macs import DuplicateMacsCommand
from .empty_prefixes import EmptyPrefixesCommand
from .iface_tags import InterfaceTagsCommand
from .subif_labels import SubinterfaceLabelsCommand
from .subif_parents import SubinterfaceParentsCommand
from .unassigned_ips import UnassignedIpsCommand
from .unparented_ips import UnparentedIpsCommand


# The subcommands nblint offers, in --help order. Registration is kept
# explicit on purpose: no import scanning, so the list stays greppable.
COMMANDS = (
    UnassignedIpsCommand,
    EmptyPrefixesCommand,
    DuplicatePrefixesCommand,
    DuplicateIpsCommand,
    UnparentedIpsCommand,
    DuplicateMacsCommand,
    DeviceBmcsCommand,
    SubinterfaceParentsCommand,
    SubinterfaceLabelsCommand,
    InterfaceTagsCommand,
    UnattachedCablesCommand,
)

COMMANDS_BY_NAME = {cmdcls.name: cmdcls for cmdcls in COMMANDS}
