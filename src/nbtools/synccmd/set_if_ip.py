from collections import namedtuple

from ..command import STDIN_ARG, SyncCommand, stdin_or
from ..exceptions import (
    ItemExistsElsewhere, UnrecognisedItem, UnrecognisedItemOnTarget)
from ..netbox import (
    get_interface_tree, get_ip_addresses_by_address, get_mac_addresses)
from ..types import DevIface, IPv4AddrWithMask, MacAddr
from ..work import (
    named_anon, named_id,
    AssignIPAddress,
    DeleteIPAddress,
    DummyUnassignIPAddress,
    ModifyIPAddress,
    ReassignIPAddress)


# One item of work: the interface to set an IP on, and the IP. Both
# halves can come off stdin, a "TARGET IP" line apiece.
TargetIp = namedtuple('TargetIp', 'target ip')


class BaseSetInterfaceIpCommand(SyncCommand):
    r"""
    Shared by set-interface-ip and set-interface-ip-by-mac.

    The two differ only in how the target interface is named, so the
    subclasses supply the type that reads one and the lookup that
    turns it into an interface.

    An item is a (target, IP) pair, and a pair per line can arrive on
    stdin -- which is what the '-' arguments are for:

        nbsync --batch --keep-going set-interface-ip-by-mac - - \
            --vrf=MGMT --status=dhcp --single --force

    fed the MAC and the IP a DHCP server just handed out, each set as
    the lease lands. The options are the same for every line; only
    the pair varies, so only the pair comes in on one.
    """
    help = 'Set IP on an interface.'

    # The type that reads this command's kind of target, and what to
    # tell the reader it looks like.
    target_type = None
    target_help = None

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--force', action='store_true', help=(
            'Remove IP from elsewhere if needed'))
        parser.add_argument('--single', action='store_true', help=(
            'Delete any other IP found here'))
        parser.add_argument('--status', default='active', choices=(
            'active', 'reserved', 'deprecated', 'dhcp', 'lacp'), help=(
                'Set status to one of the available choices'))
        parser.add_argument('--vrf', default=None, help=(
            'Set VRF'))
        parser.add_argument(
            'target', type=stdin_or(cls.target_type), help=cls.target_help)
        parser.add_argument(
            'ip', type=stdin_or(IPv4AddrWithMask), help=(
                'IPv4 address, e.g. 10.20.30.4/24. Give '
                f'"{STDIN_ARG}" for this and the target both to read '
                'the pairs from stdin instead, a "TARGET IP" line '
                'each, set as it arrives -- which needs --batch, '
                'stdin being taken'))  # FIXME: IPv4 only for now?

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_input_rows(TargetIp, [
            (args.target, cls.target_type),
            (args.ip, IPv4AddrWithMask)])
        cmd.set_options(
            force=args.force, single=args.single,
            status=args.status, vrf=args.vrf)
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._force = False
        self._single = False
        self._status = 'active'
        self._vrf = None
        self._nd_vrf = None

    def set_options(self, force=False, single=False, status='active',
                    vrf=None):
        "What to do with the IP; the same for every item"
        self._force = force
        self._single = single
        self._status = status
        self._vrf = vrf

    def resolve_interface(self, target):
        "The interface that this command's kind of target names"
        raise NotImplementedError

    @staticmethod
    def _make_named_ip(ip, id_, iface):
        dev = iface.device
        named_dev = named_id(dev.name, dev.id, parent=None)
        named_iface = named_id(iface.name, iface.id, parent=named_dev)

        if id_ is None:
            named_ip = named_anon(str(ip), parent=named_iface)
        else:
            named_ip = named_id(str(ip), id_, parent=named_iface)

        return named_ip

    def prepare(self):
        """
        Look the VRF up once, not once per item

        It is an option, so it is the same for every pair, and on a
        stream this is the difference between one read and one per
        line. A --vrf nobody has heard of stops the run here, before
        the first item: it is a mistake in the command, not in the
        input.
        """
        if self._vrf:
            vrf = self.nbapi.ipam.vrfs.get(name=self._vrf)
            if not vrf:
                raise UnrecognisedItem(('vrf', self._vrf))
            self._nd_vrf = named_id(vrf.name, vrf.id, parent=None)
        else:
            # (Both the IP we find and the VRF we want can be VRF-less.)
            self._nd_vrf = named_id('-', None, parent=None)

    def plan_one(self, value):
        iface = self.resolve_interface(value.target)
        wanted_ip = value.ip
        nd_vrf = self._nd_vrf

        # Build a list of future work.
        work_to_do = []

        # Check where the IP is already used. Through the helper, which
        # asks address= rather than the q= freeform search this used to
        # send: an indexed lookup instead of a walk over the table, and
        # the slowest of the reads this command makes is gone.
        ips = get_ip_addresses_by_address(self.nbapi, wanted_ip)
        # NOTE: for non-hardware, we'd do vminterface=iface
        cur_ips = set(self.nbapi.ipam.ip_addresses.filter(
            interface_id=iface.id))
        good_ips = set([ip for ip in ips if ip.assigned_object == iface])
        my_other_ips = cur_ips - good_ips
        elsewhere_ips = set([ip for ip in ips if ip.assigned_object != iface])

        if len(elsewhere_ips) > 1 or any(
                ip.role and ip.role.value == 'anycast'
                for ip in elsewhere_ips):
            raise NotImplementedError(
                f'was not expecting to handle Anycast IPs: '
                f'{elsewhere_ips} found elsewhere')

        # We have:
        # - good_ips = only check/fix status
        # - my_other_ips = remove if --single
        # - elsewhere_ips = remove if --force
        # print('good', good_ips, 'other', my_other_ips, 'elsewhere_ips',
        #     elsewhere_ips)

        # If found and not here, we need to delete (if force) or replace.
        if elsewhere_ips:
            first_elsewhere_ip = list(sorted(elsewhere_ips))[0]
            if self._force:
                assert len(elsewhere_ips) == 1, elsewhere_ips
                assert str(first_elsewhere_ip) == str(wanted_ip), (
                    first_elsewhere_ip, wanted_ip)

                work_to_do.append(
                    DummyUnassignIPAddress(
                        self._make_named_ip(
                            str(first_elsewhere_ip),
                            first_elsewhere_ip.id,
                            first_elsewhere_ip.assigned_object)))
                work_to_do.append(
                    ReassignIPAddress(
                        self._make_named_ip(
                            str(first_elsewhere_ip),
                            first_elsewhere_ip.id,
                            iface),
                        {
                            'assigned_object_type': 'dcim.interface',
                            'assigned_object_id': iface.id,
                            'status': self._status,
                            'vrf': nd_vrf,
                        }
                    )
                )

                # Moving it to the good IPs.
                good_ips.add(first_elsewhere_ip)
                elsewhere_ips.remove(first_elsewhere_ip)
            else:
                raise ItemExistsElsewhere(first_elsewhere_ip)

        # If other IPs are here and we have single, we need to delete
        # the others.
        if my_other_ips and self._single:
            for ip in my_other_ips:
                work_to_do.append(DeleteIPAddress(
                    self._make_named_ip(
                        str(ip),
                        ip.id,
                        ip.assigned_object)))

        # If the IP is not here yet, we need to add it.
        if not good_ips:
            work_to_do.append(AssignIPAddress(
                self._make_named_ip(
                    str(wanted_ip),
                    None,
                    iface),
                {
                    # New data.
                    'assigned_object_type': 'dcim.interface',
                    'assigned_object_id': iface.id,
                    'address': str(wanted_ip),
                    'description': '',
                    'dns_name': '',
                    'role': None,
                    'status': self._status,
                    'tags': [],
                    'tenant': None,
                    'vrf': nd_vrf,
                }
            ))

        # Lastly, fix status or VRF.
        for good_ip in good_ips:
            good_vrf_id = (good_ip.vrf.id if good_ip.vrf else None)
            if (good_ip.status.value != self._status
                    or good_vrf_id != nd_vrf.id):
                work_to_do.append(ModifyIPAddress(
                    self._make_named_ip(
                        str(good_ip),
                        good_ip.id,
                        iface),
                    {
                        'status': self._status,
                        'vrf': nd_vrf,
                    }
                ))

        return work_to_do


class SetInterfaceIpCommand(BaseSetInterfaceIpCommand):
    name = 'set-interface-ip'

    target_type = DevIface
    target_help = 'Target device and interface (e.g. mynode.example:BMC)'

    def resolve_interface(self, target: DevIface):
        # XXX: For both hw and vm?
        tgt = get_interface_tree(
            self.nbapi, target, raise_as=UnrecognisedItemOnTarget)
        if tgt.if_children:
            # We want the interface itself, not a whole subtree.
            raise UnrecognisedItemOnTarget((target, tgt.if_children))

        return tgt.if_parent


class SetInterfaceIpByMacCommand(BaseSetInterfaceIpCommand):
    name = 'set-interface-ip-by-mac'

    target_type = MacAddr
    target_help = 'Target MAC address (e.g. 11:22:33:44:55:66)'

    def resolve_interface(self, target: MacAddr):
        # XXX: For both hw and vm?
        # Through the helper rather than filter(target): that is a
        # freeform q= search, and it was trusted here to be exact.
        # get_mac_addresses() re-checks the match itself.
        macs = get_mac_addresses(self.nbapi, target)
        if len(macs) == 0:
            raise UnrecognisedItem(target)
        if len(macs) > 1:
            raise UnrecognisedItemOnTarget(macs)

        return macs[0].assigned_object
