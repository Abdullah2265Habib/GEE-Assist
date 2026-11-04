"""Keeps the refresh token between app launches ("Keep me signed in").

The token is stored in the operating system's credential store (Windows Credential Manager,
macOS Keychain, Secret Service on Linux) through ``keyring`` - never in a plain file.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

_REFRESH_TOKEN_KEY = "refresh_token"


class ISessionStore(ABC):
    @abstractmethod
    def save_refresh_token(self, token: str) -> None: ...

    @abstractmethod
    def load_refresh_token(self) -> str | None: ...

    @abstractmethod
    def clear(self) -> None: ...


class KeyringSessionStore(ISessionStore):
    def __init__(self, service_name: str):
        self._service = service_name

    def save_refresh_token(self, token: str) -> None:
        try:
            import keyring

            keyring.set_password(self._service, _REFRESH_TOKEN_KEY, token)
        except Exception:  # no usable credential store: the user simply signs in next time
            logger.warning("Could not save the session in the system credential store", exc_info=True)

    def load_refresh_token(self) -> str | None:
        try:
            import keyring

            return keyring.get_password(self._service, _REFRESH_TOKEN_KEY)
        except Exception:
            logger.warning("Could not read the session from the system credential store", exc_info=True)
            return None

    def clear(self) -> None:
        try:
            import keyring
            from keyring.errors import PasswordDeleteError

            try:
                keyring.delete_password(self._service, _REFRESH_TOKEN_KEY)
            except PasswordDeleteError:
                pass  # nothing stored
        except Exception:
            logger.warning("Could not clear the session from the system credential store", exc_info=True)


class MemorySessionStore(ISessionStore):
    """Keeps nothing between launches. Used in tests."""

    def __init__(self) -> None:
        self._token: str | None = None

    def save_refresh_token(self, token: str) -> None:
        self._token = token

    def load_refresh_token(self) -> str | None:
        return self._token

    def clear(self) -> None:
        self._token = None
