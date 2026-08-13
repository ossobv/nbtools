from collections import namedtuple

from ..command import Command
from ..device import NetboxDevice
from ..exceptions import NotFound
from ..work import (
    ModifyCable,
    UnrecognisedItemOnSource, UnrecognisedItemOnTarget,
    named_id)


SwapCableInfo = namedtuple(
    'SwapCableInfo', 'dev if_name if_dev')


class SwapCableCommand(Command):
    def set_a_interface(self, srcdevname: str, srcifacename: str):
        self._srcdevname = srcdevname
        self._srcifacename = srcifacename

    def set_b_interface(self, tgtdevname: str, tgtifacename: str):
        self._tgtdevname = tgtdevname
        self._tgtifacename = tgtifacename

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

    def _make_swapcableinfo(
            self, devname: str, ifacename: str) -> SwapCableInfo:
        dev = NetboxDevice.get_by_name(self.nbapi, devname)
        ifaces = dev.get_interfaces_by_name(
            ifacename, with_subinterfaces=False)
        if_dev = ifaces.pop(0)
        assert not ifaces, ifaces

        assert len(if_dev.cable.a_terminations) < 2, if_dev
        assert len(if_dev.cable.b_terminations) < 2, if_dev

        if len(if_dev.cable.a_terminations) != 1:
            raise UnrecognisedItemOnSource(
                f'expected connected cable to swap on {devname}:{ifacename}')
        if len(if_dev.cable.b_terminations) != 1:
            raise UnrecognisedItemOnSource(
                f'expected connected cable to swap on {devname}:{ifacename}')

        return SwapCableInfo(
            dev=dev,
            if_name=ifacename,
            if_dev=if_dev,
        )

    def _process(self):
        # Get source.
        try:
            src = self._make_swapcableinfo(
                self._srcdevname, self._srcifacename)
        except NotFound as e:
            raise UnrecognisedItemOnSource(
                (self._srcdevname, self._srcifacename)) from e

        # Get target.
        try:
            tgt = self._make_swapcableinfo(
                self._tgtdevname, self._tgtifacename)
        except NotFound as e:
            raise UnrecognisedItemOnTarget(
                (self._tgtdevname, self._tgtifacename)) from e

        # Build a list of future work.
        assert src.if_dev.link_peers_type == 'dcim.interface', src.if_dev
        assert tgt.if_dev.link_peers_type == 'dcim.interface', tgt.if_dev

        # NOTE: It does matter what we swap. We don't want to end up with
        # A1<->A2 and B1<->B2. So, find the a_terminations or b_terminations
        # through _cable_termination_key.
        id1 = src.if_dev.cable.id
        values1detached = {
            self._cable_termination_key(src.if_dev): []
        }
        values1 = {
            self._cable_termination_key(src.if_dev): [{
                'object_type': 'dcim.interface',
                # Yes! Here goes target, not source.
                'object_id': tgt.if_dev.id,
            }]
        }
        id2 = tgt.if_dev.cable.id
        values2 = {
            self._cable_termination_key(tgt.if_dev): [{
                'object_type': 'dcim.interface',
                # Yes! Here goes source, not target.
                'object_id': src.if_dev.id,
            }]
        }

        nd_srcdev = named_id(
            src.dev.device.name, src.dev.device.id, parent=None)
        nd_srciface = named_id(
            src.if_dev.name, src.if_dev.id, parent=nd_srcdev)
        nd_tgtdev = named_id(
            tgt.dev.device.name, tgt.dev.device.id, parent=None)
        nd_tgtiface = named_id(
            tgt.if_dev.name, tgt.if_dev.id, parent=nd_tgtdev)

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

        # Anything to do?
        if not work_to_do:
            self.verbose('Nothing to do')
            return

        # There is work.
        self.verbose('-----------')
        self.verbose('swap-cables')
        self.verbose('-----------')
        for work in work_to_do:
            self.print('-', work)

        self.confirm_or_die()

        for work in work_to_do:
            work.do(self.nbapi)
