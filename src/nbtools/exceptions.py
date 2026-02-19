class StartupError(ValueError):
    pass


class StateError(Exception):
    pass


class NotFound(StateError):
    pass
