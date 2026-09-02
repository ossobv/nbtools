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


class ApiError(StateError):
    """
    NetBox did not answer, or answered with a failure.

    Not a state error in spirit -- nothing is wrong with the data --
    but it travels the same path so that both tools report it in one
    line instead of a traceback. See netbox.translated_errors().
    """
    description = 'NetBox did not answer'
    hint = 'Transient: check the NetBox and proxy logs, then retry.'

    @classmethod
    def from_request_error(cls, error):
        """
        Build one from a pynetbox RequestError

        Says which request failed and how, and leaves out the response
        body that pynetbox pastes into its own message: a 408 from the
        proxy carries an HTML error page, not something to print.
        """
        response = getattr(error, 'req', None)
        if response is None:
            return cls(str(error))

        method = getattr(response.request, 'method', '?')
        return cls(
            f'{method} {response.url}: '
            f'{response.status_code} {response.reason}')


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


class TargetCountMismatch(StateError):
    description = 'There is not one target for every source'
    hint = 'Pass one --target for each switch port the gateways sit on.'
