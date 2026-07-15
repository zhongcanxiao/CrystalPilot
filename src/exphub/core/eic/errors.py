"""Typed exception hierarchy for the vendored EIC client (extracted from eic_client.py)."""

from typing import Optional


class EICClientError(Exception):
    """Exception class for EIC client errors."""

    def __init__(self, message: str = "", original_error: Optional[Exception] = None) -> None:
        if not message:
            message = ""
        # noinspection PyBroadException
        try:
            message += " [" + original_error.response.json()["message"] + "]"  # type: ignore
        except Exception:
            pass
        super(EICClientError, self).__init__(message)
        self.original_error = original_error


class UnauthorizedError(EICClientError):
    """Unauthorized to access the EIC client."""

    pass


class InvalidClientCredentialsError(EICClientError):
    """Invalid client credentials were passed to the EIC client."""

    pass


class InvalidUserCredentialsError(EICClientError):
    """Invalid user credentials were passed to the EIC client."""

    pass


class InvalidRefreshTokenError(EICClientError):
    """Invalid refresh token."""

    pass


class LoginRequiredError(EICClientError):
    """Login required."""

    pass


class NotFoundError(EICClientError):
    """Endpoint not found."""

    pass


class BadRequestError(EICClientError):
    """Bad request sent to EIC client."""

    pass
