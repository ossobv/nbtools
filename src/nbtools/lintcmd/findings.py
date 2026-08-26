"""
How the IPAM lint commands render one record.

For now, we include id, ip, status vrf for a prefix or for an IP. We may
revisit this later.
"""
from ..ipam import status_name, vrf_name
from ..util import quoted_name


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


class MultipleVrfsFinding:
    """
    One value that exists in more than one VRF.

    Rendered the way duplicate-macs renders its groups: the value, how
    many of them there are, then where each one sits -- here the VRF
    rather than the device, because the VRF is the thing that differs.
    """
    def __init__(self, value, records):
        self.value = value
        self.records = records

    def porcelain(self):
        return str(self.value)

    def __str__(self):
        detail = ', '.join(
            f'#{record.id} {vrf_name(record)}' for record in self.records)

        return f'{self.value} x{len(self.records)}: {detail}'


class InterfaceFinding:
    """
    One dcim.interface worth reporting, named device:interface.

    porcelain() prints exactly that, which is the DEV:IFACE argument
    every nbsync interface command already takes -- so a finding can
    be piped straight into one. The device name is quoted when it
    needs it: NetBox names hold spaces and colons, and an unquoted one
    runs into the note.
    """
    def __init__(self, iface, note=''):
        self.iface = iface
        self.note = note

    @property
    def value(self):
        return f'{quoted_name(self.iface.device.name)}:{self.iface.name}'

    def porcelain(self):
        return self.value

    def __str__(self):
        note = (f' {self.note}' if self.note else '')

        return f'{self.value} #{self.iface.id}{note}'
