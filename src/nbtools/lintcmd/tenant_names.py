from re import compile as re_compile

from ..command import LintCommand
from ..util import quoted_name


# What a tenant or tenant-group name has to look like. The verbose,
# punctuated name belongs in the description field: a name that reads
# like a slug is one that can be typed on a command line and put in a
# config file without quoting.
#
# A digit may lead -- names like 7eleven are in use. Two characters
# minimum, which is what the two required classes either side of the
# middle one mean, and neither end may be the dash: '-x' and 'x-' are
# names that read as a fragment of something else.
#
# Note there is no underscore in here. NetBox slugs allow one and the
# rule this replaces did too; if any name relies on that, this reports
# it.
IDENTIFIER = re_compile(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$')

# The two endpoints, and what to call a record from each in the
# listing.
KINDS = (
    ('tenant', 'tenants'),
    ('tenant-group', 'tenant_groups'),
)


def why_wrong(record):
    """
    What is wrong with this record's name, or None when nothing is

    The empty description is reported only alongside a bad name.
    DESIGN.md says the description "is supposed to have the verbose
    punctuated name", but a tenant whose name needs no punctuating has
    nothing to put there, and reporting every one of those would bury
    the names that are actually wrong.
    """
    name = str(record.name)
    if IDENTIFIER.match(name):
        return None

    reason = f'name is not slug-style ({IDENTIFIER.pattern})'
    if not str(getattr(record, 'description', '') or ''):
        return f'{reason}, and the description is empty'

    return reason


def find_bad_names(nbapi, kinds=KINDS):
    "The tenants and tenant-groups whose names are not identifier-style"
    found = []
    for kind, endpoint in kinds:
        for record in getattr(nbapi.tenancy, endpoint).all():
            reason = why_wrong(record)
            if reason is not None:
                found.append((kind, record, reason))

    return found


class TenantNameFinding:
    "One tenant or tenant-group whose name is not identifier-style"

    def __init__(self, kind, record, reason):
        self.kind = kind
        self.record = record
        self.reason = reason

    def porcelain(self):
        return str(self.record.name)

    def __str__(self):
        return (
            f'{self.kind} {quoted_name(self.record.name)} '
            f'#{self.record.id} {self.reason}')


class TenantNamesCommand(LintCommand):
    name = 'tenant-names'
    help = (
        'Find tenants and tenant-groups whose name is not slug-style. A '
        'name matching [a-z0-9][a-z0-9-]*[a-z0-9] is one that can be typed '
        'on a command line and put in a config file unquoted; the verbose, '
        'punctuated name belongs in the description. A digit may lead, two '
        'characters is the minimum, and there is no underscore in the set.')

    def find(self):
        return [
            TenantNameFinding(kind, record, reason)
            for kind, record, reason in find_bad_names(self.nbapi)]
