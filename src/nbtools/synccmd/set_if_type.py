from ..command import STDIN_ARG, SyncCommand, stdin_or
from ..exceptions import UnrecognisedItemOnTarget
from ..netbox import get_interface_tree
from ..types import DevIface
from ..work import ModifyInterface, named_id


class SetInterfaceTypeCommand(SyncCommand):
    """
    Set the type of interfaces, e.g. to bridge.

    The other half of nblint interface-types, which prints the
    interfaces whose name says they are something they are not typed
    as:

        nblint --porcelain interface-types --limit=bridge \\
            | nbsync --batch set-interface-type bridge -

    An interface that already has the type is no work.
    """
    name = 'set-interface-type'
    help = (
        'Set the type of interfaces, e.g. to bridge. Takes the '
        'output of "nblint --porcelain interface-types --limit=TYPE" '
        'on stdin.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('type', help=(
            'The NetBox interface type value to set (e.g. bridge, '
            'virtual, 1000base-t)'))
        parser.add_argument(
            'target', type=stdin_or(DevIface), nargs='+', help=(
                'Target device and interface (e.g. pve1:vmbr0). Give '
                f'"{STDIN_ARG}" to read them from stdin instead, one '
                'per line, each set as it arrives -- which needs '
                '--batch, stdin being taken'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_type(args.type)
        cmd.set_input_values(args.target, DevIface)
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._type = None

    def set_type(self, type_):
        assert type_, type_
        self._type = type_

    def plan_one(self, target: DevIface):
        iface = get_interface_tree(
            self.nbapi, target, with_subinterfaces=False,
            raise_as=UnrecognisedItemOnTarget).if_parent

        if iface.type.value == self._type:
            return []

        nd_dev = named_id(iface.device.name, iface.device.id, parent=None)
        nd_iface = named_id(iface.name, iface.id, parent=nd_dev)

        return [ModifyInterface(nd_iface, {'type': self._type})]
