from ..command import LintCommand
from .findings import InterfaceFinding


# The tags that describe a *link* rather than a port, so that carrying
# one on one end only is a contradiction. They are this setup's own
# names, which is why --tag exists.
PAIRED_TAGS = ('corelink', 'ebgp', 'fec-off')

# What a cable has to land on for this check to mean anything. A cable
# through a patch panel lands on a front port, and the tag on the
# interface at the far side of the panel is not this cable's business.
INTERFACE = 'dcim.interface'


def peers_of(iface):
    """
    The interfaces at the far end of this interface's cable

    NetBox keeps them on the record as link_peers, with
    link_peers_type saying what kind they are. Returns [] when the far
    end is not an interface at all -- see INTERFACE above.
    """
    if getattr(iface, 'link_peers_type', None) != INTERFACE:
        return []

    return list(getattr(iface, 'link_peers', None) or [])


def find_unpaired_tags(tag, ifaces):
    """
    The interfaces carrying this tag whose cable peer does not

    Returns [(iface, [peers])]. Both ends being tagged needs no extra
    lookup: an interface that carries the tag is in `ifaces`, so the
    question is only whether the peer's id is in that set.

    Interfaces with no cable are skipped -- the tag says something
    about a link, and there is no link to disagree with -- and so is a
    cable whose far end is not an interface.
    """
    tagged = {iface.id for iface in ifaces}

    found = []
    for iface in ifaces:
        if getattr(iface, 'cable', None) is None:
            continue

        untagged = [
            peer for peer in peers_of(iface) if peer.id not in tagged]
        if untagged:
            found.append((iface, untagged))

    return found


def a_note(tag, peers):
    detail = ', '.join(
        f'{peer.device.name}:{peer.name} #{peer.id}' for peer in peers)

    return f"tag '{tag}' not on the far end: {detail}"


class InterfaceTagsCommand(LintCommand):
    name = 'unpaired-interface-tags'
    help = (
        'Find interfaces carrying a link tag that the far end of their '
        'cable does not. corelink, ebgp and fec-off each describe the '
        'link rather than the port, so having one on a single end is a '
        'contradiction. Interfaces with no cable are left alone, and so '
        'are cables that land on a patch panel rather than on another '
        'interface.')

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument(
            '--tag', action='append', metavar='SLUG', help=(
                'Check this tag instead of the built-in list. Repeatable. '
                f'Default: {", ".join(PAIRED_TAGS)}.'))

    @classmethod
    def from_args(cls, nbapi, args):
        cmd = cls(nbapi)
        cmd.set_tags(args.tag or PAIRED_TAGS)
        return cmd

    def __init__(self, nbapi):
        super().__init__(nbapi)
        self._tags = PAIRED_TAGS

    def set_tags(self, tags):
        assert tags, tags
        self._tags = tuple(tags)

    def find(self):
        findings = []
        for tag in self._tags:
            # One request per tag, which is what DESIGN.md writes:
            # /dcim/interfaces/?tag=corelink. Asking for all three at
            # once would come back as a union with no way to tell
            # which interface was in it for which tag.
            ifaces = list(self.nbapi.dcim.interfaces.filter(tag=tag))

            findings.extend(
                InterfaceFinding(iface, note=a_note(tag, peers))
                for iface, peers in find_unpaired_tags(tag, ifaces))

        return findings
