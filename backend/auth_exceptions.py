"""Errors raised while talking to the authentication server.

All derive from ``GeeAssistError``, so the UI can show ``str(error)`` like any other backend error.
"""

from __future__ import annotations

from backend.exceptions import GeeAssistError


class AuthError(GeeAssistError):
    """An authentication request failed. ``status_code`` is the HTTP status (0 = no response)."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ServerUnavailableError(AuthError):
    """The authentication server could not be reached."""


class InvalidCredentialsError(AuthError):
    """Wrong username or password (401)."""


class SessionExpiredError(AuthError):
    """The stored token is missing, invalid or expired - the user must sign in again (401)."""


class AccountDisabledError(AuthError):
    """The account was disabled by an administrator (403)."""


class PermissionDeniedError(AuthError):
    """The user is signed in but not allowed to do this (403, e.g. not an admin)."""


class VerificationRequiredError(AuthError):
    """The password was right but the email address is not verified yet (403).

    ``verification_token`` lets the app check the status and resend the email.
    """

    def __init__(self, message: str, verification_token: str, email_verified: bool = False):
        super().__init__(message, 403)
        self.verification_token = verification_token
        self.email_verified = email_verified


class ConflictError(AuthError):
    """Something already exists (409): username / email / phone taken, email already verified, ...

    ``field`` names the form field the conflict is about, when it can be told from the message.
    """

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message, 409)
        self.field = field


class FieldValidationError(AuthError):
    """The server rejected some fields (422). ``field_errors`` maps field name -> message."""

    def __init__(self, message: str, field_errors: dict[str, str]):
        super().__init__(message, 422)
        self.field_errors = field_errors


class RateLimitedError(AuthError):
    """Asked again too soon (429). Try again after ``retry_after`` seconds."""

    def __init__(self, message: str, retry_after: int):
        super().__init__(message, 429)
        self.retry_after = retry_after


class NotFoundError(AuthError):
    """The user or Google sign-in session does not exist (404)."""


class InvalidRequestError(AuthError):
    """The server rejected the request (400), e.g. an admin changing their own role."""


class EmailDeliveryError(AuthError):
    """The server could not send the verification email (502)."""


class GoogleSignInUnavailableError(AuthError):
    """Google sign-in is not configured on the server (503)."""
