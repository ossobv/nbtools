from ..command import Command
from ..exceptions import UnrecognisedItemOnTarget
from ..netbox import get_interface_tree
from ..types import DevIface
from ..work import (
    DeleteInterface, ModifyInterface,
    DeleteIPAddress)


class ZapInterfaceCommand(Command):
    name = 'zap-interface'
    help = (
        'Zap (clean/wipe) properties from an interface. '
        'Keeps the interface, but wipes tags, descriptions, '
        'subinterfaces and assigned IPs. '
        'Useful to wipe target before calling migrate-interface.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('target', type=DevIface, help=(
            'Target device and interface (e.g. leaf2:swp8)'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_target_interface(args.target)
        return cmd

    def set_target_interface(self, target: DevIface):
        self._target = target

    def plan(self):
        # Get target to wipe.
        tgt = get_interface_tree(
            self.nbapi, self._target, raise_as=UnrecognisedItemOnTarget)

        # Build a list of future work.
        work_to_do = []

        # For each subinterface, remove IPs.
        for tgtiface in tgt.if_children:
            # # From "ensrc1.1234" make "entgt2.1234".
            # srcifacesuffix = srciface.name[len(src.if_name):]
            # assert srcifacesuffix.startswith('.'), srcifacesuffix
            # tgtifacename = f'{tgt.if_name}{srcifacesuffix}'
            # tgtiface = find_elem(
            #     tgt.if_children, (lambda x: x.name == tgtifacename))
            self._add_work(
                work_to_do, tgt, tgtiface)

        # Add work for the parent interface.
        self._add_work(
            work_to_do, tgt, tgt.if_parent)

        return work_to_do

    def _add_work(
            self, work_to_do, tgt, tgtiface):
        raise NotImplementedError(f'delete interface {tgt} {tgtiface}')
        # Here we do:
        DeleteIPAddress  # on all subinterface-addresses
        DeleteInterface  # on all subinterfaces
        DeleteIPAddress  # on all interface-addresses
        ModifyInterface  # wiping all settings...
        # ...except for NAME and TYPE, I guess..

        # at least: vlans, labels/tags

        # # Get source IPs.
        # srcipaddrs = list(self.nbapi.ipam.ip_addresses.filter(
        #     assigned_object_id=srciface.id))
        #
        # # Check source. We expect a VRF on it.
        # if not srciface.vrf:
        #     raise UnrecognisedItemOnSource(
        #         f'missing VRF on {src.dev.name}:{srciface}')
