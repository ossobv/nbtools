from collections import namedtuple

from ..command import Command
from ..device import NetboxDevice
from ..exceptions import NotFound, UnrecognisedItemOnTarget
from ..work import (
    DeleteInterface, ModifyInterface,
    DeleteIPAddress)


ZapInterfaceInfo = namedtuple(
    'ZapInterfaceInfo', 'dev if_name if_parent if_children')


class ZapInterfaceCommand(Command):
    def set_target_interface(self, tgtdevname: str, tgtifacename: str):
        self._tgtdevname = tgtdevname
        self._tgtifacename = tgtifacename

    @staticmethod
    def _check_that_child_interface_names_start_with_interface(
            ifaces, ifacename) -> None:
        startswith = f'{ifacename}.'
        for iface in ifaces:
            if not iface.name.startswith(startswith):
                raise NotImplementedError(
                    f'expected "{iface}" to start with "{startswith}"')

    def _make_zapinterfaceinfo(
            self, devname: str, ifacename: str) -> ZapInterfaceInfo:
        dev = NetboxDevice.get_by_name(self.nbapi, devname)
        ifaces = dev.get_interfaces_by_name(ifacename)
        parentiface = ifaces.pop(0)
        self._check_that_child_interface_names_start_with_interface(
            ifaces, ifacename)

        return ZapInterfaceInfo(
            dev=dev,
            if_name=ifacename,
            if_parent=parentiface,
            if_children=ifaces,
        )

    def _process(self):
        # Get target to wipe.
        try:
            tgt = self._make_zapinterfaceinfo(
                self._tgtdevname, self._tgtifacename)
        except NotFound as e:
            raise UnrecognisedItemOnTarget(
                (self._tgtdevname, self._tgtifacename)) from e

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

        # Anything to do?
        if not work_to_do:
            self.verbose('Nothing to do')
            return

        # There is work.
        self.verbose('-------------')
        self.verbose('zap-interface')
        self.verbose('-------------')
        for work in work_to_do:
            self.print('-', work)

        self.confirm_or_die()

        for work in work_to_do:
            work.do(self.nbapi)

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
        #         f'missing VRF on {src.dev.device.name}:{srciface}')
