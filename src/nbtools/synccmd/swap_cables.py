from ..command import SyncCommand
from ..exceptions import (
    UnrecognisedItemOnSource, UnrecognisedItemOnTarget)
from ..netbox import get_interface_tree
from ..types import DevIface
from ..work import (
    ModifyCable,
    named_id)


class SwapCableCommand(SyncCommand):
    name = 'swap-cables'
    help = (
        'Swap two connected cables. Changes A1<->B1 and A2<->B2 to '
        'A1<->B2 and A2<->B1.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('iface1', type=DevIface, help=(
            'One connected device and interface (e.g. pve1:enmlx1)'))
        parser.add_argument('iface2', type=DevIface, help=(
            'Other connected device and interface (e.g. pve1:enmlx0)'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_a_interface(args.iface1)
        cmd.set_b_interface(args.iface2)
        return cmd

    def set_a_interface(self, source: DevIface):
        self._source = source

    def set_b_interface(self, target: DevIface):
        self._target = target

    @staticmethod
    def _cable_termination_key(if_dev):
        a_terminations = if_dev.cable.a_terminations
        assert len(a_terminations) < 2, if_dev
        b_terminations = if_dev.cable.b_terminations
        assert len(b_terminations) < 2, if_dev

        if a_terminations and a_terminations[0].id == if_dev.id:
            return 'a_terminations'
        elif b_terminations and b_terminations[0].id == if_dev.id:
            return 'b_terminations'
        return None

    def _get_cabled_interface(self, devif: DevIface, raise_as):
        "Get the interface, insisting that it has a cable on both ends"
        tree = get_interface_tree(
            self.nbapi, devif, with_subinterfaces=False, raise_as=raise_as)
        if_dev = tree.if_parent

        assert len(if_dev.cable.a_terminations) < 2, if_dev
        assert len(if_dev.cable.b_terminations) < 2, if_dev

        if len(if_dev.cable.a_terminations) != 1:
            raise UnrecognisedItemOnSource(
                f'expected connected cable to swap on {devif}')
        if len(if_dev.cable.b_terminations) != 1:
            raise UnrecognisedItemOnSource(
                f'expected connected cable to swap on {devif}')

        return tree

    def plan(self):
        # Get source.
        src = self._get_cabled_interface(
            self._source, raise_as=UnrecognisedItemOnSource)

        # Get target.
        tgt = self._get_cabled_interface(
            self._target, raise_as=UnrecognisedItemOnTarget)

        # Build a list of future work.
        assert src.if_parent.link_peers_type == 'dcim.interface', src.if_parent
        assert tgt.if_parent.link_peers_type == 'dcim.interface', tgt.if_parent

        # NOTE: It does matter what we swap. We don't want to end up with
        # A1<->A2 and B1<->B2. So, find the a_terminations or b_terminations
        # through _cable_termination_key.
        id1 = src.if_parent.cable.id
        values1detached = {
            self._cable_termination_key(src.if_parent): []
        }
        values1 = {
            self._cable_termination_key(src.if_parent): [{
                'object_type': 'dcim.interface',
                # Yes! Here goes target, not source.
                'object_id': tgt.if_parent.id,
            }]
        }
        id2 = tgt.if_parent.cable.id
        values2 = {
            self._cable_termination_key(tgt.if_parent): [{
                'object_type': 'dcim.interface',
                # Yes! Here goes source, not target.
                'object_id': src.if_parent.id,
            }]
        }

        nd_srcdev = named_id(
            src.dev.name, src.dev.id, parent=None)
        nd_srciface = named_id(
            src.if_parent.name, src.if_parent.id, parent=nd_srcdev)
        nd_tgtdev = named_id(
            tgt.dev.name, tgt.dev.id, parent=None)
        nd_tgtiface = named_id(
            tgt.if_parent.name, tgt.if_parent.id, parent=nd_tgtdev)

        work_to_do = [
            # Must detach first:
            # https://github.com/netbox-community/netbox/issues/4890
            # ['Duplicate termination found for dcim.interface 12: cable 34']
            ModifyCable(
                named_id(f'#{id1}', id1, parent=nd_srciface), values1detached),
            ModifyCable(
                named_id(f'#{id2}', id2, parent=nd_tgtiface), values2),
            ModifyCable(
                named_id(f'#{id1}', id1, parent=nd_srciface), values1),
        ]

        return work_to_do
