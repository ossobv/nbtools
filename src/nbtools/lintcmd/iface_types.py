from ..command import LintCommand
from ..exceptions import StartupError
from ..util import split_subinterface

from .findings import InterfaceFinding


# The interface types a name gives away, as (name prefix, type). A
# Proxmox host calls its Linux bridges vmbr0, vmbr1, ..., so an
# interface by that name that is not a bridge was filed by hand, or by
# an import that guessed from the speed.
#
# A subinterface of one is not: vmbr0.20 is the VLAN interface on the
# bridge, and virtual is right for that.
TYPES_BY_PREFIX = (
    ('vmbr', 'bridge'),
)

# What --limit takes: one wanted type. A --porcelain run needs it,
# because the DEV:IFACE it prints does not say which type to set, and
# nbsync set-interface-type is told that once for the whole stream.
LIMITS = tuple(sorted({wanted for _prefix, wanted in TYPES_BY_PREFIX}))


class InterfaceTypesCommand(LintCommand):
    name = 'interface-types'
    help = (
        'Find interfaces whose name says what type they are, but whose '
        'type does not. For now that is the Proxmox bridges: an '
        'interface named vmbr* should be type=bridge.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--limit', choices=LIMITS, help=(
            'Report only the interfaces that should be this type. '
            'Required with --porcelain: the output names the interface '
            'and not the type, so a stream holding more than one type '
            'cannot be safely fed to a single set-interface-type.'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_limit(args.limit)
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._limit = None

    def set_limit(self, limit):
        assert limit in LIMITS or limit is None, limit
        self._limit = limit

    def set_porcelain(self):
        if self._limit is None:
            raise StartupError(
                f'--porcelain needs --limit ({", ".join(LIMITS)}) for '
                f'{self.name}: the output does not say which type to set')

        super().set_porcelain()

    def find(self):
        findings = []
        for prefix, wanted in TYPES_BY_PREFIX:
            if self._limit not in (None, wanted):
                continue

            # name__isw ignores case, so the prefix is checked again
            # here: VMBR0 is not a name Proxmox makes.
            ifaces = self.nbapi.dcim.interfaces.filter(
                name__isw=prefix, type__n=wanted)

            findings.extend(
                InterfaceFinding(
                    iface, note=f'is type={iface.type.value}, '
                    f'wanted type={wanted}')
                for iface in ifaces
                if iface.name.startswith(prefix)
                and not split_subinterface(iface.name))

        return findings
