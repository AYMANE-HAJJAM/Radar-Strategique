"""Application-level errors mapped to stable API error codes."""


class AppError(Exception):
    """Base application error."""


class UnauthorizedError(AppError):
    pass


class StaleActionError(AppError):
    pass


class RunAlreadyActiveError(AppError):
    pass


class InvalidCallbackError(AppError):
    pass


class SourceUnavailableError(AppError):
    pass


class DailyLimitExceededError(AppError):
    pass
