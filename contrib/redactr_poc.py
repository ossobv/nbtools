#!/usr/bin/env python3
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_interface
from os import environ
from unittest import TestCase, expectedFailure, main as unittest_main
from typing import List, Tuple
import hashlib
import json
import re
import secrets
import sys

# from faker import Faker
# fake = Faker()


class Replacement:
    pass


class StringReplacement(Replacement):
    """
    Placeholder for a replacement. To be stringified at the second pass.
    """
    def __init__(self, replacer, get_args):
        self.replacer = replacer
        self.get_args = get_args

    def __str__(self):
        self.replacer.done_feeding()  # we can calculate replacements now
        replacement = self.replacer.get(self.get_args)
        assert isinstance(replacement, str), (
            self.replacer, self.get_args, '=', replacement)
        return replacement


class ReplacerBase:
    """
    Replacer base class. Provide a salt if you want reproducible replacements.
    """
    _MAX_CONFLICTS = 100  # in case of hash conflicts, try with a next digit

    def __init__(self, salt: bytes | None = None):
        self.salt: bytes = (
            salt if salt is not None else secrets.token_bytes(16))

    def __call__(self, text: str) -> StringReplacement | None:
        """
        Return a StringReplacement or None if this is not something we handle.

        The StringReplacement is not processed until the first stringification
        happens. At first stringification, done_feeding() is called so the
        replacements can be calculated with all info.
        """
        return self.make_replacement(text)

    def _hash_with_counter(self, text_bytes: bytes, counter: int) -> int:
        # sha256(salt || text || counter)
        h = hashlib.sha256(
            self.salt + text_bytes + counter.to_bytes(4, 'big')).digest()
        return int.from_bytes(h, 'big')


class IpReplacer(ReplacerBase):
    """
    Replace IPv4/IPv6 addresses with random-but-valid addresses.

    - Same input -> same output within the same instance (cache).
    - Different inputs -> different outputs (no reuse).
    - Supports "1.2.3.4" and "1.2.3.4/24".
    - Valid networks stay valid, so "1.2.3.0/24" does not become "1.2.3.4/24".
    - By default preserves category (private/loopback/multicast/public).
    - Pass `salt` (bytes or hex string) to make mappings reproducible
      across runs.
    """
    # Pools as lists of (start_int, end_int) for IPv4 and IPv6.
    POOLS = {
        4: {
            'private': [
                (int(IPv4Address('10.0.0.0')),
                 int(IPv4Address('10.255.255.255'))),
                (int(IPv4Address('172.16.0.0')),
                 int(IPv4Address('172.31.255.255'))),
                (int(IPv4Address('192.168.0.0')),
                 int(IPv4Address('192.168.255.255'))),
            ],
            'loopback': [
                (int(IPv4Address('127.0.0.0')),
                 int(IPv4Address('127.255.255.255'))),
            ],
            'multicast': [
                (int(IPv4Address('224.0.0.0')),
                 int(IPv4Address('239.255.255.255'))),
            ],
            # public pool: some big reserved blocks that won't collide
            # with real public space
            'public': [
                # CGN /10 (large)
                (int(IPv4Address('100.64.0.0')),
                 int(IPv4Address('100.127.255.255'))),
                # benchmark/testing
                (int(IPv4Address('198.18.0.0')),
                 int(IPv4Address('198.19.255.255'))),
                # TEST-NET-3 (small, recognisable)
                (int(IPv4Address('203.0.113.0')),
                 int(IPv4Address('203.0.113.255'))),
                # TEST-NET-1
                (int(IPv4Address('192.0.2.0')),
                 int(IPv4Address('192.0.2.255'))),
            ],
        },
        6: {
            'private': [
                (int(IPv6Address('fd00::')),
                 int(IPv6Address('fdff:ffff:ffff:ffff:ffff:ffff:ffff:ffff'))),
            ],
            'loopback': [
                (int(IPv6Address('::1')), int(IPv6Address('::1'))),
            ],
            'multicast': [
                (int(IPv6Address('ff00::')),
                 int(IPv6Address('ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff'))),
            ],
            'public': [
                # small doc range, plus more - IPv6 space is huge, so
                # hashing will spread nicely
                (int(IPv6Address('2001:db8::')),
                 int(IPv6Address('2001:db8:0:0:0:0:0:ffff'))),
            ],
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._text_mapping = {}     # input_str -> output_str
        self._ip_mapping = {}       # input_ip -> output_ip
        self._ip_used = set()       # (ip_version, input_ip)

        self._unprocessed = set()

    # ---------- helpers ----------

    def _cumulative_range(self, ranges: List[Tuple[int, int]]):
        parts = []
        cum = 0
        for start, end in ranges:
            size = end - start + 1
            parts.append((start, end, cum))
            cum += size
        return cum, parts

    def _pick_from_union_by_hash(
            self, ranges: List[Tuple[int, int]], hash_int: int) -> int:

        total, parts = self._cumulative_range(ranges)
        offset = hash_int % total
        # find range that contains offset
        for start, end, cum_start in parts:
            size = end - start + 1
            if offset < cum_start + size:
                inner = offset - cum_start
                return start + inner
        # should not happen
        raise RuntimeError("range selection failed")

    # ---------- public API ----------

    def make_replacement(self, text: str) -> StringReplacement | None:
        """
        Feed a token. This is a pre-replacement step.

        This way we can check all values before doing something.
        """
        if '/' in text:
            try:
                bin_ip = ip_interface(text)
            except ValueError:
                return None
        else:
            try:
                bin_ip = ip_address(text)
            except ValueError:
                return None

        self._unprocessed.add((text, bin_ip))

        return StringReplacement(self, text)

    def done_feeding(self):
        # Process all items at once.
        if self._unprocessed:
            for text_ip, bin_ip in self._unprocessed:
                self._set(text_ip, bin_ip)
            self._unprocessed.clear()

    def get(self, get_args):
        return self._text_mapping.get(get_args)

    def _set(self, text_ip, bin_ip):
        # If we're feeding data after stringify we might have cached
        # text mappings already. Normally only during tests, because in
        # other cases you want everything fed before doing the work.
        if text_ip in self._text_mapping:
            return

        # support ip/prefix like "10.0.0.1/24"
        if '/' in text_ip:
            prefix = bin_ip.network.prefixlen
            out_ip = self._replace_ip_obj(bin_ip.ip)
            new_ip = f'{out_ip}/{prefix}'
        else:
            new_ip = self._replace_ip_obj(bin_ip)

        self._text_mapping[text_ip] = new_ip

    def _replace_ip_obj(self, ip_obj):
        key = str(ip_obj)
        if out := self._ip_mapping.get(key):
            return out

        if (ip_obj.is_unspecified  # 0.0.0.0 or ::
                or (ip_obj.version == 4 and int(ip_obj) == 0xff_ff_ff_ff)):
            self._ip_mapping[key] = key
            return key

        pools = self.POOLS[ip_obj.version][self._classify(ip_obj)]
        text_bytes = key.encode('utf-8')
        for attempt in range(self._MAX_CONFLICTS):
            hashval = self._hash_with_counter(text_bytes, attempt)
            cand_int = self._pick_from_union_by_hash(pools, hashval)
            if (ip_obj.version, cand_int) not in self._ip_used:
                break
        else:
            raise RuntimeError(f'exhausted candidates for {ip_obj!s}')

        self._ip_used.add((ip_obj.version, cand_int))
        if ip_obj.version == 4:
            new_ip = IPv4Address(cand_int)
        elif ip_obj.version == 6:
            new_ip = IPv6Address(cand_int)
        else:
            raise NotImplementedError(ip_obj.version)

        out = self._ip_mapping[key] = str(new_ip)
        return out

    def _classify(self, ip_obj):
        if ip_obj.is_private:
            return 'private'
        if ip_obj.is_loopback:
            return 'loopback'
        if ip_obj.is_multicast:
            return 'multicast'
        return 'public'


class MacReplacer(ReplacerBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # TODO: Allow more MAC address styles?
        self._mac_re = re.compile(
            r'(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$')

        self._text_mapping = {}
        self._bin_mapping = {}
        self._bin_used = set()  # == _bin_mapping.keys()

        self._unprocessed = set()

    def make_replacement(self, text: str) -> str | None:
        if not self._mac_re.match(text):
            return None

        separators = set(
            ch for ch in text if ch not in '0123456789abcdefABCDEF')
        if len(separators) != 1:
            # This is not a mac, if you're mixing ':' and '-'.
            return None
        hexdigits = text.replace(''.join(separators), '')
        letters = [ch for ch in hexdigits if ch in 'abcdefABCDEF']

        if not letters:
            is_upper = False  # default
        elif all(ch.isupper() for ch in letters):
            is_upper = True
        elif all(ch.islower() for ch in letters):
            is_upper = False
        else:
            is_upper = None  # mixed

        bin_mac = int(hexdigits, 16)

        # Add to list of unprocessed items.
        self._unprocessed.add((text, bin_mac, is_upper))

        return StringReplacement(self, text)

    def done_feeding(self):
        # Process all items at once.
        if self._unprocessed:
            for text_mac, bin_mac, is_upper in self._unprocessed:
                self._set(text_mac, bin_mac, is_upper)
            self._unprocessed.clear()

    def get(self, get_args):
        return self._text_mapping.get(get_args)

    def _set(self, text_mac, bin_mac, is_upper):
        # If we're feeding data after stringify we might have cached
        # text mappings already. Normally only during tests, because in
        # other cases you want everything fed before doing the work.
        if text_mac in self._text_mapping:
            return

        if cand_mac := self._bin_mapping.get(bin_mac):
            pass
        elif bin_mac == 0x0000_0000_0000 or bin_mac == 0xffff_ffff_ffff:
            cand_mac = bin_mac
        else:
            # Make an unused MAC based on a hash of the original.
            for attempt in range(self._MAX_CONFLICTS):
                hashval = self._hash_with_counter(
                    bin_mac.to_bytes(6, 'big'), attempt)
                # Valid by copying the entire OUI. This should not be a
                # privacy risk, and might even explain things better.
                # ("A-ha, Cisco MAC, so a switch.")
                cand_mac = (
                    bin_mac & 0xffff_ff00_0000 |
                    hashval & 0x0000_00ff_ffff)
                if cand_mac not in self._bin_used:
                    break
            else:
                raise RuntimeError(f'exhausted candidates for {hex(bin_mac)}')

        self._bin_used.add(cand_mac)
        self._bin_mapping[bin_mac] = cand_mac
        self._text_mapping[text_mac] = self._tweak_mac(
            self._make_mac(cand_mac), is_upper)

    @staticmethod
    def _make_mac(numeric_mac: int) -> str:
        return ':'.join(f'{b:02x}' for b in numeric_mac.to_bytes(6, 'big'))

    @staticmethod
    def _tweak_mac(text_mac: str, is_upper: bool | None) -> str:
        """
        TODO: is_upper should take a Format, which also can set "-" or
        ":" separator.
        """
        if is_upper is True:
            return text_mac.upper()
        if is_upper is False:
            return text_mac.lower()
        # TODO: Make random case?
        return text_mac


# class NameReplacer(ReplacerBase):
#     def __init__(self):
#         self.cache = {}
#
#     def replace(self, text: str) -> str:
#         # crude heuristic: replace if it looks like a name (letters+spaces)
#         if not re.match(r'^[A-Za-z][A-Za-z\s\-]+$', text):
#             return text
#         if text in self.cache:
#             return self.cache[text]
#
#         # XXX fake_name = fake.name()
#         fake_name = self.cache[text] = 'FIXME'  # fake_name
#         return fake_name


def is_datetime(text):
    return is_datetime._re.match(text)
is_datetime._re = re.compile(  # noqa
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([.]\d+)?Z?$')


class StringReplacer(ReplacerBase):
    def __init__(self):
        self._replacements = {}
        self._unprocessed = set()
        self._processed = {}

        try:
            with open('redactr_poc.stringreplacer.json', 'r') as fp:
                for line in fp:
                    enabled, from_, to = json.loads(line)
                    if enabled and from_ != to:
                        self._replacements[from_] = to
        except FileNotFoundError:
            pass

    def make_replacement(self, text: str) -> StringReplacement | None:
        if text == '':
            return None
        if is_datetime(text):
            return None

        if text not in self._unprocessed:
            self._unprocessed.add(text)

        return StringReplacement(self, text)

    def done_feeding(self):
        # Process all items at once.
        for text in sorted(self._unprocessed):
            if text not in self._processed:
                replaced = self._replacements.get(text, text)
                self._processed[text] = replaced
        self._unprocessed.clear()

        with open('redactr_poc.stringreplacer.json', 'w') as fp:
            for from_, to in sorted(self._replacements.items()):
                assert from_ != to, (from_, to)
                fp.write(json.dumps([1, from_, to]) + '\n')
            for from_, to in sorted(self._processed.items()):
                if from_ == to:
                    fp.write(json.dumps([0, from_, to]) + '\n')

    def get(self, get_args):
        return self._processed.get(get_args)


class RedactrEngine:
    """
    FIXME: This should work on tokens. And then we can reuse this for json,
    yaml, plain-text, etc.

    FIXME: We would like to feed all possible tokens to the replacers first,
    and do the replacements later. For IP addresses, I'd like to be able
    to have a 10.20.0.0/16 and some 10.20.30.40 IPs, and when replaces,
    they should change, but fall withing the same range: 10.88.0.0/16
    and 10.88.123.45.
    """
    def __init__(self, salt=None):
        self.replacers = (
            # IpReplacer(salt=salt),
            MacReplacer(salt=salt),
            # DISABLED: this replaces too much, like "GET" and "POST"
            # NameReplacer(salt=salt),
            StringReplacer(),
        )

    def process(self, obj):
        # First pass: feed the tokens to the replacers, so they can come
        # up with a strategy (if desired).
        with_replacements = self._process(obj, self.replacers)

        # Second pass: do the actual replacement by stringification.
        return self._process(with_replacements, [])

    def _process(self, obj, processors):
        if isinstance(obj, dict):
            return {k: self._process(v, processors) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._process(v, processors) for v in obj]
        elif isinstance(obj, str):
            for fn in processors:
                if (new := fn(obj)) and new is not None:
                    return new
            return obj          # just return orig
        elif isinstance(obj, StringReplacement):
            assert processors == [], processors
            return str(obj)     # only seen the second pass
        else:
            assert isinstance(obj, (type(None), bool, float, int)), obj
            return obj


class IpReplacerTestCase(TestCase):
    def test_process(self):
        inputs = (
            ('10.123.13.22/24', '10.255.129.207/24'),
            ('10.123.13.22/24', '10.255.129.207/24'),
            ('10.123.13.22/24', '10.255.129.207/24'),
            ('10.123.13.22/24', '10.255.129.207/24'),
            # XXX: this is wrong. We want the others to be in the same network.
            ('10.123.13.26/24', '10.88.220.150/24'),
            ('10.123.13.26/24', '10.88.220.150/24'),
            ('10.123.13.26/24', '10.88.220.150/24'),
            ('10.123.13.26/24', '10.88.220.150/24'),
            ('10.129.66.96/31', '10.99.82.127/31'),
            ('10.129.66.96/31', '10.99.82.127/31'),
            ('2.2.144.64/31', '100.126.90.204/31'),
            ('2.2.144.64/31', '100.126.90.204/31'),
            ('2.2.144.66/31', '100.73.145.212/31'),
            ('2.2.144.66/31', '100.73.145.212/31'),
            ('1.2.196.152/31', '100.74.214.116/31'),
            ('1.2.196.152/31', '100.74.214.116/31'),
            ('1.2.196.232/31', '100.64.108.22/31'),
            ('1.2.196.232/31', '100.64.108.22/31'),
            ('1.2.196.234/31', '100.100.11.114/31'),
            ('1.2.196.234/31', '100.100.11.114/31'),
            ('1.2.197.0/31', '100.86.61.88/31'),
            ('1.2.197.0/31', '100.86.61.88/31'),
            ('1.2.198.166/31', '100.126.29.0/31'),
            ('1.2.198.166/31', '100.126.29.0/31'),
            ('1.2.198.168/31', '100.75.199.252/31'),
            ('1.2.198.168/31', '100.75.199.252/31'),
            ('1.2.199.252/31', '100.127.53.84/31'),
            ('1.2.199.252/31', '100.127.53.84/31'),
            ('1.2.199.252/31', '100.127.53.84/31'),
            ('1.2.199.252/31', '100.127.53.84/31'),
            ('10.125.50.56/31', '10.188.206.188/31'),
            ('10.125.50.56/31', '10.188.206.188/31'),
            ('10.125.52.212/31', '10.164.74.6/31'),
            ('10.125.52.212/31', '10.164.74.6/31'),
            ('10.125.52.214/31', '10.251.183.194/31'),
            ('10.125.52.214/31', '10.251.183.194/31'),
            ('10.124.0.14/31', '10.179.74.199/31'),
            ('10.124.0.14/31', '10.179.74.199/31'),
            ('10.124.1.40/31', '10.179.36.168/31'),
            ('10.124.1.40/31', '10.179.36.168/31'),
        )
        replacements = []
        r = IpReplacer(salt=b'abcd')
        for from_, to in inputs:
            replacement = r(from_)
            replacements.append(replacement)
            # print('-', from_, repr(replacement))
        for (from_, to), replacement in zip(inputs, replacements):
            # print(f'        ({from_!r}, {str(replacement)!r}),')
            self.assertEqual(str(replacement), to)

    def test_ipv4(self):
        r = IpReplacer(salt=b'abcd')
        self.assertEqual(str(r('1.2.3.4')), '100.84.255.5')
        self.assertEqual(str(r('88.88.144.65/31')), '100.116.188.159/31')

    @expectedFailure  # NotImplemented
    def test_ipv4_network_stays_valid(self):
        r = IpReplacer(salt=b'abcd')
        self.assertEqual(str(r('1.2.3.4/31')), '100.84.255.4/31')
        self.assertEqual(str(r('10.20.30.129/25')), '10.151.230.203/25')
        self.assertEqual(str(r('10.20.30.128/25')), '10.64.140.128/25')

    @expectedFailure  # NotImplemented
    def test_ipv4_special_stays_special(self):
        # Very special case
        r = IpReplacer()
        self.assertEqual(str(r('0.0.0.0')), '0.0.0.0')
        self.assertEqual(str(r('255.255.255.255')), '255.255.255.255')

        # Regular special case: keep 0 and 255
        r = IpReplacer(salt=b'abcd')
        self.assertEqual(str(r('1.2.3.0')), '100.113.34.0')
        self.assertEqual(str(r('1.2.3.255')), '100.113.34.255')

    def test_ipv6(self):
        r = IpReplacer(salt=b'abcd')
        self.assertEqual(
            str(r('2001:db8::200e/31')),
            'fde8:5897:ad77:c63f:d64b:6910:2d6f:e124/31')

    @expectedFailure  # NotImplemented
    def test_ipv6_ip4(self):
        r = IpReplacer(salt=b'abcd')
        self.assertEqual(r.replace('::ffff:1.2.3.4/31'), '::ffff:?.?.?.?/31')


class MacReplacerTestCase(TestCase):
    def test_case(self):
        r = MacReplacer(salt=b'abcd')
        # mixed case
        self.assertEqual(
            str(r('00:30:ab:AB:CD:EF')), '00:30:ab:0c:98:36')
        # lowercase
        self.assertEqual(
            str(r('00:30:ab:ab:cd:ef')), '00:30:ab:0c:98:36')
        # uppercase
        self.assertEqual(
            str(r('00:30:AB:AB:CD:EF')), '00:30:AB:0C:98:36')

    def test_extremes(self):
        r = MacReplacer()
        self.assertEqual(
            str(r('00:00:00:00:00:00')), '00:00:00:00:00:00')
        self.assertEqual(
            str(r('ff:ff:ff:ff:ff:ff')), 'ff:ff:ff:ff:ff:ff')
        self.assertEqual(
            str(r('FF:FF:FF:FF:FF:FF')), 'FF:FF:FF:FF:FF:FF')

    def test_match_no_match(self):
        r = MacReplacer()

        self.assertIsNone(r('aap-noot-mies'))

        self.assertIsInstance(r('00:11:22:33:44:55'), StringReplacement)
        self.assertEqual(len(str(r('00:11:22:33:44:55'))), 17)

        self.assertIsNone(r(':11:22:33:44:55'))
        self.assertIsNone(r('00:11:22:33:44:5'))

    def test_salt(self):
        # salt
        r = MacReplacer(salt=b'abcd')
        self.assertEqual(str(r('00:11:22:33:44:55')), '00:11:22:df:44:8f')
        self.assertEqual(str(r('00:11:22:33:44:54')), '00:11:22:1a:a4:d8')

        # replace again, still yields same
        self.assertEqual(str(r('00:11:22:33:44:55')), '00:11:22:df:44:8f')

        # diff salt
        r = MacReplacer(salt=b'1234')
        self.assertEqual(str(r('00:11:22:33:44:55')), '00:11:22:29:56:a1')
        self.assertEqual(str(r('00:11:22:33:44:54')), '00:11:22:20:42:4a')

        # same salt as earlier again
        r = MacReplacer(salt=b'abcd')
        self.assertEqual(str(r('00:11:22:33:44:54')), '00:11:22:1a:a4:d8')
        self.assertEqual(str(r('00:11:22:33:44:55')), '00:11:22:df:44:8f')


def main(salt=None):
    data = open(sys.argv[1]).read()
    parsed = json.loads(data)
    engine = RedactrEngine(salt=salt)
    replaced = engine.process(parsed)
    print(json.dumps(replaced, indent=2))


if __name__ == '__main__':
    if environ.get('RUNTESTS', '') not in ('', '0', 'no'):
        unittest_main()
        assert False, 'does not get here'

    main(salt=b'abcd')
