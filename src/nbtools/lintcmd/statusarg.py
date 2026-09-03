"""
The --status flag the IPAM lint commands share.

Two of them are asked to leave reserved records alone: a reserved
prefix or address is one held on purpose with nothing in it. Generally
those are used to denote that the real IP/prefix lives in another
NetBox/source-of-truth.

The flag is an allowlist: what you name is what gets reported.
"""
from argparse import ArgumentTypeError

from ..ipam import status_name


# The value that turns the filtering off rather than naming a status.
ALL = 'all'


class StatusFilter:
    """
    Which records a run reports, as resolved from --status.

    Two shapes, on purpose. Naming statuses builds the include kind,
    and the report then holds those and nothing else. Naming none --
    the default, and 'all' -- builds the exclude kind, so a status
    this code has never heard of is still reported: a NetBox can be
    configured with choices of its own, and a run that asked for
    nothing in particular should not silently drop them.
    """
    def __init__(self, include=None, exclude=()):
        self.include = (None if include is None else tuple(include))
        self.exclude = tuple(exclude)

    def __contains__(self, status):
        if self.include is not None:
            return status in self.include

        return status not in self.exclude

    def allows(self, record):
        "Whether this record's status is one being reported"
        return status_name(record) in self


class StatusArgument:
    """
    The --status flag for one kind of record, and what it parses to.

    Built with the statuses that kind can have and the ones left out
    unless asked for, then used from the three places a command's flag
    lives: add_argument() puts it on the parser, from_args() reads it
    back, and filter_for() turns that -- or a test's plain list -- into
    the StatusFilter that find() consults.
    """
    def __init__(self, noun, statuses, skipped_by_default=(), reason=''):
        for status in skipped_by_default:
            assert status in statuses, status

        self.noun = noun
        self.statuses = tuple(statuses)
        self.skipped_by_default = tuple(skipped_by_default)
        self.reason = reason

    @property
    def reported_by_default(self):
        "The statuses a run without --status reports"
        return tuple(
            status for status in self.statuses
            if status not in self.skipped_by_default)

    def add_argument(self, parser):
        parser.add_argument(
            '--status', action='append', type=self.parse_value,
            metavar='STATUS', help=self.help())

    def help(self):
        skipped = ', '.join(self.skipped_by_default)
        parts = [
            f'Report only {self.noun} with this status. Repeatable, or '
            f'comma separated. One of: {", ".join(self.statuses)}.']

        if self.skipped_by_default:
            parts.append(
                f'Default: {",".join(self.reported_by_default)} -- '
                f'{skipped} is left out'
                + (f', {self.reason}' if self.reason else '')
                + f'. Pass "{ALL}" for every status, {skipped} included.')

        return ' '.join(parts)

    def parse_value(self, value):
        "One --status value: a status, several comma separated, or 'all'"
        chosen = []

        for word in value.split(','):
            word = word.strip()
            if word != ALL and word not in self.statuses:
                raise ArgumentTypeError(
                    f'{word!r}: expected {ALL} or one of '
                    f'{", ".join(self.statuses)}')
            chosen.append(word)

        return chosen

    def from_args(self, args):
        "Every status --status was given, the repeats flattened out"
        return [word for value in (args.status or ()) for word in value]

    def filter_for(self, statuses=None):
        """
        The StatusFilter that list of statuses asks for

        Nothing, or an empty list, is the default; see StatusFilter for
        why that is not the same as naming every status.
        """
        if not statuses:
            return StatusFilter(exclude=self.skipped_by_default)

        if ALL in statuses:
            return StatusFilter()

        return StatusFilter(include=statuses)
