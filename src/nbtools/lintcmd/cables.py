from ..command import LintCommand, NoPorcelainMixin
from ..util import quoted_name


# The two ends NetBox gives a cable. They are lists rather than single
# terminations: one cable can land on several ports, as a breakout
# does.
SIDES = ('a', 'b')


def terminations(cable, side):
    "The terminations on one end of a cable, possibly none"
    return list(getattr(cable, f'{side}_terminations', None) or [])


def where(termination):
    """
    Render one termination as device:interface, best effort

    A cable does not have to land on an interface -- a front port or a
    circuit termination is a cable end too -- and those nest something
    of a different shape. So this reads what is there rather than
    assuming an interface.
    """
    obj = getattr(termination, 'object', None)
    if obj is None:
        return '?'

    name = str(getattr(obj, 'name', '?'))
    device = getattr(obj, 'device', None)
    if device is None:
        return name

    return f'{quoted_name(device.name)}:{name}'


def rendered_side(cable, side):
    "The ends on one side of a cable, or '<none>' when there are none"
    found = terminations(cable, side)
    if not found:
        return '<none>'

    return ', '.join(where(termination) for termination in found)


def find_unattached_cables(cables):
    "The cables that do not have both ends attached"
    unattached = list(cables)
    assert all(
        not terminations(cable, 'a') or not terminations(cable, 'b')
        for cable in unattached)
    return unattached


class CableFinding:
    """
    One cable with an end missing.

    Note that this only detects direct connections to the next device.
    Cables attached to some multimode device are counted as connected,
    even when the other end might not lead somewhere.
    """
    def __init__(self, cable):
        self.cable = cable

    def porcelain(self):
        "Do not return anything useful until we have a standardized format"
        return NotImplemented

    def __str__(self):
        status = getattr(self.cable, 'status', None)
        status = str(getattr(status, 'value', status or '-'))

        return (
            f'cable #{self.cable.id} status={status} '
            f'a={rendered_side(self.cable, "a")} '
            f'b={rendered_side(self.cable, "b")}')


class UnattachedCablesCommand(NoPorcelainMixin, LintCommand):
    name = 'unattached-cables'
    help = (
        'Find physical cables that do not have both ends attached.')

    def find(self):
        unattached_cables = self.nbapi.dcim.cables.filter(unterminated=True)
        return [
            CableFinding(cable)
            for cable in sorted(
                find_unattached_cables(unattached_cables),
                key=(lambda cable: cable.id))]
