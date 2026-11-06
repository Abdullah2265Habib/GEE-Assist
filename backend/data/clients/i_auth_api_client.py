from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IAuthApiClient(ABC):
    """HTTP client for the GEE-Assist authentication server (GEE-Assist-Backend).

    Every method returns the decoded JSON body, or raises an ``AuthError`` subclass
    (see ``backend.auth_exceptions``) describing what went wrong.
    """

    # ------------------------------------------------------------------ public
    @abstractmethod
    def health(self) -> bool:
        """GET /health - True if the server answers."""

    @abstractmethod
    def signup(self, payload: dict[str, str]) -> dict[str, Any]:
        """POST /auth/signup"""

    @abstractmethod
    def login(self, username: str, password: str) -> dict[str, Any]:
        """POST /auth/login"""

    @abstractmethod
    def refresh(self, refresh_token: str) -> dict[str, Any]:
        """POST /auth/refresh"""

    @abstractmethod
    def me(self, access_token: str) -> dict[str, Any]:
        """GET /auth/me"""

    # ------------------------------------------------------------ verification
    @abstractmethod
    def verification_status(self, verification_token: str) -> dict[str, Any]:
        """GET /auth/verification-status"""

    @abstractmethod
    def resend_verification_email(self, verification_token: str, email: str | None = None) -> dict[str, Any]:
        """POST /auth/verify-email/resend"""

    # ------------------------------------------------------------------ Google
    @abstractmethod
    def google_start(self) -> dict[str, Any]:
        """POST /auth/google/start"""

    @abstractmethod
    def google_poll(self, session_id: str) -> dict[str, Any] | None:
        """POST /auth/google/poll - the login response, or None while the user has not finished (202)."""

    # ------------------------------------------------------------------- admin
    @abstractmethod
    def list_users(self, access_token: str, skip: int = 0, limit: int = 50) -> dict[str, Any]:
        """GET /admin/users"""

    @abstractmethod
    def get_user(self, access_token: str, user_id: str) -> dict[str, Any]:
        """GET /admin/users/{user_id}"""

    @abstractmethod
    def update_user_role(self, access_token: str, user_id: str, role: str) -> dict[str, Any]:
        """PATCH /admin/users/{user_id}/role"""

    @abstractmethod
    def update_user_status(self, access_token: str, user_id: str, is_active: bool) -> dict[str, Any]:
        """PATCH /admin/users/{user_id}/status"""
