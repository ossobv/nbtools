from ..command import LintCommand
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
    """
    The cables that do not have both ends attached

    Both-ends-empty is included. DESIGN.md asks for the one-ended
    kind, which is the one that looks plugged in from one side and
    therefore misleads; a cable attached to nothing at all is the same
    fault with nobody to notice it, and it costs nothing to report.
    """
    return [
        cable for cable in cables
        if not (terminations(cable, 'a') and terminations(cable, 'b'))]


class CableFinding:
    """
    One cable with an end missing.

    porcelain() prints the id. There is no nbsync command that takes a
    cable, so there is nothing better to pipe this into yet; the id is
    what the record is found by in the UI.
    """
    def __init__(self, cable):
        self.cable = cable

    def porcelain(self):
        return str(self.cable.id)

    def __str__(self):
        status = getattr(self.cable, 'status', None)
        status = str(getattr(status, 'value', status or '-'))

        return (
            f'cable #{self.cable.id} status={status} '
            f'a={rendered_side(self.cable, "a")} '
            f'b={rendered_side(self.cable, "b")}')


class UnattachedCablesCommand(LintCommand):
    name = 'unattached-cables'
    help = (
        'Find cables that do not have both ends attached. One end plugged '
        'in and the other not is a cable that looks connected from one '
        'side; a cable attached to nothing at all is reported too.')

    def find(self):
        return [
            CableFinding(cable)
            for cable in sorted(
                find_unattached_cables(self.nbapi.dcim.cables.all()),
                key=(lambda cable: cable.id))]
