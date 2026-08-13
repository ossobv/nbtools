from collections import namedtuple
from ipaddress import IPv4Interface


__all__ = ('DevIface', 'IPv4AddrWithMask', 'MacAddr')


IPv4AddrWithMask = IPv4Interface


class DevIface(namedtuple('DevIface', 'device interface')):
    """
    Takes 'leaf1:eth0', holds device='leaf1', interface='eth0'

    Split on the *last* colon: device names are free-form and do hold
    colons, e.g. 'FREE (was-planned: node3.example.com):BMC'. Interface
    names do not.
    """
    def __new__(cls, dev_iface_str):
        try:
            device, interface = dev_iface_str.rsplit(':', 1)
        except ValueError as e:
            raise ValueError('argument must be DEV:IFACE') from e

        return super().__new__(cls, device, interface)

    def __str__(self):
        return f'{self.device}:{self.interface}'


class MacAddr:
    @staticmethod
    def parse(mac):
        mac = mac.lower()
        if ':' in mac:
            parts = mac.split(':')  # 01:23:45:67:89:ab
            if len(parts) != 6:
                return None
            joined = ''.join(parts)
        elif '.' in mac:
            parts = mac.split('.')  # 0123.4567.89ab
            if len(parts) != 3:
                return None
            joined = ''.join(parts)
        else:
            return None

        if len(joined) != 12 or any(
                ch not in '0123456789abcdef' for ch in joined):
            return None

        return ':'.join(joined[i:i+2] for i in range(0, 12, 2))

    def __init__(self, mac_str):
        parsed = self.parse(mac_str)
        if parsed is None:
            raise ValueError(f'{mac_str!r} does not look like a valid MAC')

        self._value = parsed

    def __str__(self):
        return self._value
