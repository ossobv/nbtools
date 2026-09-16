from .cables import UnattachedCablesCommand
from .dev_bmcs import DeviceBmcsCommand
from .dup_in_vrfs import DuplicateIpsCommand, DuplicatePrefixesCommand
from .dup_macs import DuplicateMacsCommand
from .empty_prefixes import EmptyPrefixesCommand
from .iface_cables import UnattachedInterfacesCommand
from .iface_tags import InterfaceTagsCommand
from .iface_types import InterfaceTypesCommand
from .subif_labels import SubinterfaceLabelsCommand
from .subif_parents import SubinterfaceParentsCommand
from .tenant_names import TenantNamesCommand
from .unassigned_ips import UnassignedIpsCommand
from .unparented_ips import UnparentedIpsCommand


# The subcommands nblint offers, in --help order. Registration is kept
# explicit on purpose, so the list stays greppable.
COMMANDS = (
    # IPs/prefixes.
    UnassignedIpsCommand,
    EmptyPrefixesCommand,
    DuplicatePrefixesCommand,
    DuplicateIpsCommand,
    UnparentedIpsCommand,

    # Physical interfaces, MACs and VRFs.
    DuplicateMacsCommand,
    DeviceBmcsCommand,
    SubinterfaceParentsCommand,
    SubinterfaceLabelsCommand,

    # Interface configurations: types, tags, vlans and cabling.
    InterfaceTypesCommand,
    InterfaceTagsCommand,
    UnattachedCablesCommand,
    UnattachedInterfacesCommand,

    # Naming/grouping.
    TenantNamesCommand,
)

COMMANDS_BY_NAME = {cmdcls.name: cmdcls for cmdcls in COMMANDS}
