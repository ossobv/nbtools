"""
How the IPAM lint commands render one record.

For now, we include id, ip, status vrf for a prefix or for an IP. We may
revisit this later.
"""
from ..ipam import status_name, vrf_name


class RecordFinding:
    """
    One NetBox record, rendered as id, value, status and VRF.

    Subclasses name the field the value comes from. The value is also
    what porcelain() prints, since that is the handle a person or an
    nbsync command would name the record by.
    """
    field = None    # 'address' or 'prefix'

    def __init__(self, record, note=''):
        self.record = record
        self.note = note

    @property
    def value(self):
        return str(getattr(self.record, self.field))

    def porcelain(self):
        return self.value

    def __str__(self):
        note = (f' {self.note}' if self.note else '')

        return (
            f'{self.value} #{self.record.id} '
            f'status={status_name(self.record)} '
            f'vrf={vrf_name(self.record)}{note}')


class IpFinding(RecordFinding):
    "One ipam.ip_address worth reporting"
    field = 'address'


class PrefixFinding(RecordFinding):
    "One ipam.prefix worth reporting"
    field = 'prefix'
