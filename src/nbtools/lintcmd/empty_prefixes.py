from ..command import LintCommand
from ..ipam import IpamIndex, prefix_sort_key
from ..netbox import get_all_ip_addresses, get_all_prefixes

from .findings import PrefixFinding
from .statusarg import StatusArgument


# The families --family takes. Spelled as the strings NetBox uses in
# the query, converted to int for the filter.
FAMILIES = ('4', '6')

# The --status flag: which prefixes get reported.
#
# Reserved is the one left out by default. Container is deliberately
# *not*: a container is meant to hold other prefixes rather than
# addresses, but an empty container holds neither, so it is a finding
# -- name the statuses without it to drop those.
STATUS = StatusArgument(
    'prefixes', ('container', 'reserved', 'deprecated', 'active'),
    skipped_by_default=('reserved',),
    reason=(
        'a reserved prefix is a range somebody else hands the addresses '
        'out of, so empty is its normal state'))


# The --role flag: which prefix roles get reported.
#
# Unlike the statuses, roles are records every NetBox defines for
# itself, so there is no list to pick from. That is why this flag can
# exclude as well as include: a name reports only that role, a !name
# leaves that role out. Naming anything replaces the default. The
# empty name is the unset role: --role='' reports only the prefixes
# without one, --role='!' leaves those out.
#
# By default we skip 3rd-party, because we use it to mark prefixes as
# owned by someone else. We cannot check for IPs in those. We cannot
# always use --status=reserved for this, as that deselects them from
# routing access lists.
ROLE_ALL = 'all'
ROLES_SKIPPED_BY_DEFAULT = ('3rd-party',)


def role_slug(prefix):
    "The slug of the prefix role, or None when it has none"
    role = getattr(prefix, 'role', None)
    if role is None:
        return None

    return str(getattr(role, 'slug', role))


class RoleFilter:
    """
    Which prefix roles a run reports, as resolved from --role.

    A prefix is reported when its role is one of the included, if any
    are named, and not one of the excluded. A prefix without a role
    goes by the empty slug, so '' includes those and '!' excludes
    them.
    """
    def __init__(self, include=(), exclude=()):
        self.include = tuple(include)
        self.exclude = tuple(exclude)

    def allows(self, prefix):
        "Whether this prefix's role is one being reported"
        slug = role_slug(prefix) or ''
        if self.include and slug not in self.include:
            return False

        return slug not in self.exclude

    @classmethod
    def for_roles(cls, roles=None):
        """
        The RoleFilter that list of role words asks for.

        Nothing, or an empty list, is the default: every role but
        3rd-party. 'all' among the words drops the filtering.
        """
        if not roles:
            return cls(exclude=ROLES_SKIPPED_BY_DEFAULT)

        if ROLE_ALL in roles:
            return cls()

        return cls(
            include=(word for word in roles if not word.startswith('!')),
            exclude=(word[1:] for word in roles if word.startswith('!')))


def parse_roles(value):
    """
    One --role value: a slug or a !slug, or several comma separated.

    An empty word is not a mistake but the unset role, so --role=''
    and --role='!' pass through as '' and '!'.
    """
    return [word.strip() for word in value.split(',')]


def find_empty_prefixes(
        prefixes, addresses, statuses=None, roles=None):
    """
    The prefixes that hold neither an address nor a smaller prefix.

    Both arguments are whole tables. Containment is worked out per
    VRF: a prefix in one VRF is not filled by an address in another.
    """
    index = IpamIndex(prefixes, addresses)

    return [
        prefix for prefix in prefixes
        if (statuses is None or statuses.allows(prefix))
        and (roles is None or roles.allows(prefix))
        and index.is_empty_prefix(prefix)]


class EmptyPrefixesCommand(LintCommand):
    name = 'empty-prefixes'
    help = (
        'Find prefixes that hold nothing: no address and no smaller '
        'prefix inside them. They should probably not exist. '
        'By default --status=reserved is skipped, as is --role=3rd-party. '
        'These are assumed to be in-progress or out of our control.'
        'Use --status=all and role=all to see them anyway.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--family', choices=FAMILIES, help=(
            'Report only this address family. Both, by default.'))
        STATUS.add_argument(parser)
        parser.add_argument(
            '--role', action='append', type=parse_roles,
            metavar='ROLE', help=(
                'Report only prefixes with this role, by slug, or leave '
                'the role out with a leading (shell-quoted0 \'!\'. '
                'Repeatable, or comma separated. Default: '
                + ','.join(f'!{role}' for role in ROLES_SKIPPED_BY_DEFAULT)
                + f'; naming any role replaces that. Pass "{ROLE_ALL}" '
                'for every role. The empty role is the unset one: '
                '--role=\'\' for only the prefixes without a role, '
                '--role=\'!\' to leave those out.'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_family(args.family)
        cmd.set_statuses(STATUS.from_args(args))
        cmd.set_roles(
            [word for value in (args.role or ()) for word in value])
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._family = None
        self._statuses = STATUS.filter_for()
        self._roles = RoleFilter.for_roles()

    def set_family(self, family):
        assert family in FAMILIES or family is None, family
        self._family = family

    def set_statuses(self, statuses):
        """
        Report only prefixes with these statuses, 'all' for every one.

        Nothing, or an empty list, leaves the default in place: every
        status but the reserved.
        """
        self._statuses = STATUS.filter_for(statuses)

    def set_roles(self, roles):
        """
        Report only prefixes with these roles; a !role leaves one out.

        Nothing, or an empty list, leaves the default in place: every
        role but 3rd-party. 'all' reports every role, and '' stands
        for no role at all, so '!' leaves out the prefixes without one.
        """
        self._roles = RoleFilter.for_roles(roles)

    def find(self):
        family = (int(self._family) if self._family else None)

        prefixes = get_all_prefixes(self.nbapi, family=family)
        addresses = get_all_ip_addresses(self.nbapi, family=family)

        return [
            PrefixFinding(prefix)
            for prefix in sorted(
                find_empty_prefixes(
                    prefixes, addresses, statuses=self._statuses,
                    roles=self._roles),
                key=prefix_sort_key)]
