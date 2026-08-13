class StartupError(ValueError):
    pass


class StateError(Exception):
    """
    Base for errors about the state we found in NetBox.

    Subclasses set 'description' (what is wrong) and optionally 'hint'
    (what the user might do about it). The CLI reports both. Do not use
    __doc__ for this: python -OO strips docstrings, and a class without
    its own docstring gets None instead of the parent one.
    """
    description = 'Unexpected state'
    hint = None


class NotFound(StateError):
    description = 'Something does not seem to exist'
    hint = 'Check your arguments.'


class ItemExistsElsewhere(StateError):
    description = 'Something exists elsewhere already'
    hint = 'Check arguments, or force-delete/replace.'


class UnrecognisedItem(StateError):
    description = 'Something does not seem to exist'
    hint = 'Check your (target) arguments.'


class UnrecognisedItemOnSource(StateError):
    description = 'Something expected in the source does not exist'
    hint = 'Check your arguments.'


class UnrecognisedItemOnTarget(StateError):
    description = (
        'Something exists on target that does not exist in the source')
    hint = 'You should maybe remove it.'
