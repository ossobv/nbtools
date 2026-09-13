from re import compile as re_compile

from ..command import LintCommand
from ..util import quoted_name


# What a tenant or tenant-group name has to look like. The verbose,
# punctuated name belongs in the description field: a name that reads
# like a slug is one that can be typed on a command line and put in a
# config file without quoting.
#
# A digit may lead -- names like 7eleven are in use -- an optional
# dashes in between, like the-acme-corp.
PATTERN = r'^[a-z0-9](-?[a-z0-9])*$'
IDENTIFIER = re_compile(PATTERN)

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
        f'Find tenants and tenant-groups whose name is not slug-style: '
        f'{PATTERN}')

    def find(self):
        return [
            TenantNameFinding(kind, record, reason)
            for kind, record, reason in find_bad_names(self.nbapi)]
