"""Keeps the refresh token between app launches ("Keep me signed in").

Next to the token it keeps the time the saved session expires (seconds since the
epoch), so the app can ask for a new sign-in once that time has passed.

The token is stored in the operating system's credential store (Windows Credential Manager,
macOS Keychain, Secret Service on Linux) through ``keyring`` - never in a plain file.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

_REFRESH_TOKEN_KEY = "refresh_token"
_EXPIRES_AT_KEY = "session_expires_at"


class ISessionStore(ABC):
    @abstractmethod
    def save_refresh_token(self, token: str) -> None: ...

    @abstractmethod
    def load_refresh_token(self) -> str | None: ...

    @abstractmethod
    def save_expiry(self, expires_at: float) -> None: ...

    @abstractmethod
    def load_expiry(self) -> float | None: ...

    @abstractmethod
    def clear(self) -> None: ...


class KeyringSessionStore(ISessionStore):
    def __init__(self, service_name: str):
        self._service = service_name

    def save_refresh_token(self, token: str) -> None:
        self._set(_REFRESH_TOKEN_KEY, token)

    def load_refresh_token(self) -> str | None:
        return self._get(_REFRESH_TOKEN_KEY)

    def save_expiry(self, expires_at: float) -> None:
        self._set(_EXPIRES_AT_KEY, repr(float(expires_at)))

    def load_expiry(self) -> float | None:
        value = self._get(_EXPIRES_AT_KEY)
        try:
            return float(value) if value else None
        except ValueError:
            return None

    def clear(self) -> None:
        for key in (_REFRESH_TOKEN_KEY, _EXPIRES_AT_KEY):
            self._delete(key)

    # ------------------------------------------------------------- keyring access
    def _set(self, key: str, value: str) -> None:
        try:
            import keyring

            keyring.set_password(self._service, key, value)
        except Exception:  # no usable credential store: the user simply signs in next time
            logger.warning("Could not save the session in the system credential store", exc_info=True)

    def _get(self, key: str) -> str | None:
        try:
            import keyring

            return keyring.get_password(self._service, key)
        except Exception:
            logger.warning("Could not read the session from the system credential store", exc_info=True)
            return None

    def _delete(self, key: str) -> None:
        try:
            import keyring
            from keyring.errors import PasswordDeleteError

            try:
                keyring.delete_password(self._service, key)
            except PasswordDeleteError:
                pass  # nothing stored
        except Exception:
            logger.warning("Could not clear the session from the system credential store", exc_info=True)


class MemorySessionStore(ISessionStore):
    """Keeps nothing between launches. Used in tests."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: float | None = None

    def save_refresh_token(self, token: str) -> None:
        self._token = token

    def load_refresh_token(self) -> str | None:
        return self._token

    def save_expiry(self, expires_at: float) -> None:
        self._expires_at = expires_at

    def load_expiry(self) -> float | None:
        return self._expires_at

    def clear(self) -> None:
        self._token = None
        self._expires_at = None
