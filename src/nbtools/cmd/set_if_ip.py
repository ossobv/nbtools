from ..command import Command
from ..device import NetboxDevice
from ..exceptions import (
    ItemExistsElsewhere, NotFound, UnrecognisedItem,
    UnrecognisedItemOnTarget)
from ..work import (
    named_anon, named_id,
    AssignIPAddress,
    DeleteIPAddress,
    DummyUnassignIPAddress,
    ModifyIPAddress,
    ReassignIPAddress)


class SetInterfaceIpCommand(Command):
    def set_target_interface(self, tgtdevname: str, tgtifacename: str):
        self._tgtmac = None
        self._tgtdevname = tgtdevname
        self._tgtifacename = tgtifacename

    def set_target_interface_by_mac(self, mac: str):
        self._tgtmac = mac
        self._tgtdevname = None
        self._tgtifacename = None

    def set_ip(self, ip, force=False, single=False, status='active', vrf=None):
        self._ip = ip
        self._force = force
        self._single = single
        self._status = status
        self._vrf = vrf

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

    def _process(self):
        # Get target to wipe.
        if self._tgtdevname:
            # XXX: For both hw and vm?
            try:
                dev = NetboxDevice.get_by_name(self.nbapi, self._tgtdevname)
                ifaces = dev.get_interfaces_by_name(self._tgtifacename)
            except NotFound as e:
                raise UnrecognisedItemOnTarget(
                    (self._tgtdevname, self._tgtifacename)) from e
            if len(ifaces) != 1:
                raise UnrecognisedItemOnTarget((self._tgtdevname, ifaces))
            iface = ifaces[0]

        elif self._tgtmac:
            # XXX: For both hw and vm?
            macs = [mac for mac in self.nbapi.dcim.mac_addresses.filter(
                self._tgtmac)]
            if len(macs) == 0:
                raise UnrecognisedItem(self._tgtmac)
            if len(macs) > 1:
                raise UnrecognisedItemOnTarget(macs)

            iface = macs[0].assigned_object
            dev = NetboxDevice(self.nbapi, iface.device)
        else:
            raise NotImplementedError

        if self._vrf:
            vrf = self.nbapi.ipam.vrfs.get(name=self._vrf)
            if not vrf:
                raise UnrecognisedItem(('vrf', self._vrf))
            nd_vrf = named_id(vrf.name, vrf.id, parent=None)
        else:
            vrf = None
            nd_vrf = named_id('-', None, parent=None)

        # Build a list of future work.
        work_to_do = []

        # Check where the IP is already used.
        ips = list(self.nbapi.ipam.ip_addresses.filter(self._ip))
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
                assert str(first_elsewhere_ip) == str(self._ip), (
                    first_elsewhere_ip, self._ip)

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
                    str(self._ip),
                    None,
                    iface),
                {
                    # New data.
                    'assigned_object_type': 'dcim.interface',
                    'assigned_object_id': iface.id,
                    'address': str(self._ip),
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
            if (good_ip.status.value != self._status
                    or good_ip.vrf.id != nd_vrf.id):
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

        # Anything to do?
        if not work_to_do:
            self.verbose('Nothing to do')
            return

        # There is work.
        self.verbose('----------------')
        self.verbose('set-interface-ip')
        self.verbose('---------------')
        for work in work_to_do:
            self.print('-', work)

        self.confirm_or_die()

        for work in work_to_do:
            work.do(self.nbapi)
