from .bmc_macs import BmcMacsCommand
from .cables import UnattachedCablesCommand
from .dup_macs import DuplicateMacsCommand
from .dup_vrfs import DuplicateIpsCommand, DuplicatePrefixesCommand
from .empty_prefixes import EmptyPrefixesCommand
from .iface_tags import InterfaceTagsCommand
from .parent_if_vrfs import ParentInterfaceVrfsCommand
from .subif_labels import SubinterfaceLabelsCommand
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
    SubinterfaceLabelsCommand,
    ParentInterfaceVrfsCommand,
    BmcMacsCommand,
    InterfaceTagsCommand,
    UnattachedCablesCommand,
)

COMMANDS_BY_NAME = {cmdcls.name: cmdcls for cmdcls in COMMANDS}
