from ..command import LintCommand
from .findings import InterfaceFinding


# The tag that says this interface is expected to carry VLANs. This
# setup's own name, so --tag exists to say otherwise.
VLAN_TAG = 'closso_roth'

# The two 802.1Q modes that make sense for such a port. NetBox offers
# two more -- 'tagged-all' and 'q-in-q' -- and neither says which
# VLANs the port carries, which is the thing this check is about.
ACCESS = 'access'
TAGGED = 'tagged'
WANTED_MODES = (ACCESS, TAGGED)


def mode_of(iface):
    "The 802.1Q mode of an interface as a bare word, or None"
    mode = getattr(iface, 'mode', None)
    if mode is None:
        return None

    return str(getattr(mode, 'value', mode))


def tagged_vlans_of(iface):
    return list(getattr(iface, 'tagged_vlans', None) or [])


def untagged_vlan_of(iface):
    return getattr(iface, 'untagged_vlan', None)


def wrong_vlans(iface):
    """
    Why this interface's VLAN setup is wrong, or None when it is right

    Tagged wants one or more tagged VLANs; access wants exactly one
    untagged VLAN and, since untagged_vlan is a single field, "exactly
    one" is "one that is set".

    Tagged VLANs on an access port are reported too. DESIGN.md says
    "appropriate VLANs" rather than listing that case, but an access
    port carrying tagged VLANs contradicts its own mode, so it is hard
    to read as appropriate.
    """
    mode = mode_of(iface)

    if mode not in WANTED_MODES:
        found = (mode if mode else '<none>')
        return (
            f'mode {found}, wanted '
            f'{" or ".join(WANTED_MODES)}')

    tagged = tagged_vlans_of(iface)
    untagged = untagged_vlan_of(iface)

    if mode == TAGGED:
        if not tagged:
            return 'mode tagged but no tagged vlans'
        return None

    if untagged is None:
        return 'mode access but no untagged vlan'

    if tagged:
        return f'mode access but also {len(tagged)} tagged vlans'

    return None


def find_wrong_vlans(ifaces):
    "The interfaces whose mode and VLANs do not agree"
    found = []
    for iface in ifaces:
        note = wrong_vlans(iface)
        if note is not None:
            found.append((iface, note))

    return found


class InterfaceVlansCommand(LintCommand):
    name = 'interface-vlans'
    help = (
        'Find tagged interfaces whose 802.1Q mode and VLANs do not agree. '
        'An interface tagged closso_roth should be in Tagged mode with one '
        'or more tagged VLANs, or in Access mode with exactly one untagged '
        'VLAN. Anything else -- no mode, Tagged-all, a mode with no VLANs '
        'to go with it -- does not say which VLANs the port carries.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--tag', default=VLAN_TAG, metavar='SLUG', help=(
            f'Check the interfaces carrying this tag (default: {VLAN_TAG})'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_tag(args.tag)
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._tag = VLAN_TAG

    def set_tag(self, tag):
        assert tag, tag
        self._tag = tag

    def find(self):
        return [
            InterfaceFinding(iface, note=f"tag '{self._tag}': {note}")
            for iface, note in find_wrong_vlans(
                self.nbapi.dcim.interfaces.filter(tag=self._tag))]
