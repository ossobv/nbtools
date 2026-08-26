from .bmc_macs import BmcMacsCommand
from .cables import UnattachedCablesCommand
from .discovered import DiscoveredItemsCommand
from .dup_macs import DuplicateMacsCommand
from .dup_vrfs import DuplicateIpsCommand, DuplicatePrefixesCommand
from .empty_prefixes import EmptyPrefixesCommand
from .iface_tags import InterfaceTagsCommand
from .iface_vlans import InterfaceVlansCommand
from .parent_if_vrfs import ParentInterfaceVrfsCommand
from .subif_labels import SubinterfaceLabelsCommand
from .tenant_names import TenantNamesCommand
from .unassigned_ips import UnassignedIpsCommand
from .unparented_ips import UnparentedIpsCommand


# The subcommands nblint offers, in --help order: the IPAM ones, then
# the interface ones, then the rest. Registration is kept explicit on
# purpose: no import scanning, so the list stays greppable.
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
    InterfaceVlansCommand,

    UnattachedCablesCommand,
    DiscoveredItemsCommand,
    TenantNamesCommand,
)

COMMANDS_BY_NAME = {cmdcls.name: cmdcls for cmdcls in COMMANDS}
