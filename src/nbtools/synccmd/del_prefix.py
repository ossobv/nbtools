from ..command import STDIN_ARG, SyncCommand, stdin_or
from ..exceptions import (
    AmbiguousItem, ItemNotEmpty, NotFound, UnrecognisedItem)
from ..ipam import GLOBAL_VRF, IpamIndex, network_of, vrf_arg
from ..netbox import get_all_ip_addresses, get_all_prefixes
from ..types import VrfPrefix
from ..work import DeletePrefix, named_id


def index_prefixes(prefixes):
    """
    Index prefix records by the (network, VRF name) pair naming them

    A list per key rather than a single record: NetBox does not stop
    the same prefix being created twice in one VRF, and deleting by
    name has to refuse rather than guess when it was.
    """
    by_key = {}
    for prefix in prefixes:
        key = (network_of(prefix), vrf_arg(prefix))
        by_key.setdefault(key, []).append(prefix)

    return by_key


class DeletePrefixCommand(SyncCommand):
    """
    Delete prefixes, named as PREFIX@VRF.

    The other half of nblint empty-prefixes:

        nblint --porcelain empty-prefixes | xargs nbsync delete-prefix

    A '-' takes the values off stdin instead, one per line, each
    deleted as it arrives. That is not another way of saying the same
    thing: a list long enough for xargs to split into several runs
    would plan, list and confirm once per batch, and this does it
    once.

    Emptiness is re-checked here before anything goes. The linter's
    answer was true when it ran, and a prefix that has gained an
    address since is one somebody started using -- so this refuses it
    rather than taking the pipe's word for it. --force says otherwise.
    """
    name = 'delete-prefix'
    help = (
        'Delete prefixes, named as PREFIX@VRF (an empty VRF being the '
        'global table). Made to be fed from "nblint --porcelain '
        'empty-prefixes". Each prefix is re-checked for being empty '
        'before it goes, because the listing that named it is older '
        'than this run.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--force', action='store_true', help=(
            'Delete a prefix that is no longer empty. Whatever is inside '
            'it stays: NetBox does not cascade, so the addresses are '
            'left with no prefix over them.'))
        parser.add_argument(
            'prefix', type=stdin_or(VrfPrefix), nargs='+',
            metavar='PREFIX@VRF', help=(
                'Prefix and VRF, e.g. "10.1.2.0/24@vrf-red", or '
                '"10.1.2.0/24@" for the global table. Give '
                f'"{STDIN_ARG}" to read them from stdin instead, one '
                'per line, each deleted as it arrives -- which needs '
                '--batch, stdin being taken'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_input_values(args.prefix, VrfPrefix)
        if args.force:
            cmd.set_force()
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._force = False

        # What prepare() reads, and plan_one() then asks.
        self._by_key = None
        self._by_vrf_name = None
        self._index = None

    def set_force(self, force=True):
        self._force = force

    @staticmethod
    def _named_vrf(name, by_name):
        "Name the VRF the way other work lines name their device"
        if not name:
            # 'global', the same word nblint prints in its vrf= column,
            # rather than the empty string the *argument* spells it
            # with. This line is read by somebody about to confirm a
            # delete, so it says the table rather than echoing the
            # syntax.
            return named_id(GLOBAL_VRF, None, parent=None)

        vrf = by_name.get(name)
        if vrf is None:
            raise UnrecognisedItem(('vrf', name))

        return named_id(vrf.name, vrf.id, parent=None)

    @staticmethod
    def _find_one(wanted: VrfPrefix, by_key):
        "The single prefix record this argument names"
        found = by_key.get((wanted.prefix, wanted.vrf), [])
        if not found:
            raise NotFound(str(wanted))

        if len(found) > 1:
            raise AmbiguousItem(
                (str(wanted), [record.id for record in found]))

        return found[0]

    def prepare(self):
        """
        Read the three tables once, not once per prefix

        A --porcelain pipe can hand this hundreds of them, and
        IpamIndex is what empty-prefixes found them with in the first
        place. On a stream that also fixes the answer at the start of
        the run: a prefix this run has itself emptied still looks
        full and is refused, and the next nblint run will name it
        again. Re-reading three tables a line would cost more than
        the streaming saves.
        """
        prefixes = get_all_prefixes(self.nbapi)
        addresses = ([] if self._force else get_all_ip_addresses(self.nbapi))

        self._by_key = index_prefixes(prefixes)
        self._by_vrf_name = {
            vrf.name: vrf for vrf in self.nbapi.ipam.vrfs.all()}
        self._index = IpamIndex(prefixes, addresses)

    def plan_one(self, wanted: VrfPrefix):
        "The delete for one PREFIX@VRF, if it may go"
        # The VRF first, so that a name nobody has heard of says so.
        # Looking the prefix up first would report it missing from a
        # VRF that does not exist either, which sends the reader
        # looking for the wrong thing.
        nd_vrf = self._named_vrf(wanted.vrf, self._by_vrf_name)
        record = self._find_one(wanted, self._by_key)

        if not self._force and not self._index.is_empty_prefix(record):
            raise ItemNotEmpty(str(wanted))

        return [DeletePrefix(named_id(
            str(wanted.prefix), record.id, parent=nd_vrf))]
