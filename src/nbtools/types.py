from ipaddress import IPv4Interface


__all__ = ('IPv4AddrWithMask', 'MacAddr')


IPv4AddrWithMask = IPv4Interface


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
