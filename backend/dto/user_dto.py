"""User / authentication DTOs passed between the UI and the backend services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(frozen=True)
class UserDTO:
    id: str
    username: str
    full_name: str
    role: str
    is_active: bool = True
    email: str | None = None
    phone_number: str | None = None
    email_verified: bool = False
    auth_provider: str = "local"
    created_at: datetime | None = None
    last_login_at: datetime | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def initials(self) -> str:
        parts = [p for p in self.full_name.split() if p]
        letters = "".join(p[0] for p in parts[:2]) or self.username[:2]
        return letters.upper()

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "UserDTO":
        return cls(
            id=str(data["id"]),
            username=data["username"],
            full_name=data.get("full_name") or data["username"],
            role=data.get("role", "user"),
            is_active=bool(data.get("is_active", True)),
            email=data.get("email"),
            phone_number=data.get("phone_number"),
            email_verified=bool(data.get("email_verified", False)),
            auth_provider=data.get("auth_provider") or "local",
            created_at=_parse_datetime(data.get("created_at")),
            last_login_at=_parse_datetime(data.get("last_login_at")),
        )


@dataclass(frozen=True)
class SignupDTO:
    """What the signup form collects."""

    full_name: str
    email: str
    phone_number: str
    username: str
    password: str

    def to_api(self) -> dict[str, str]:
        return {
            "full_name": self.full_name,
            "email": self.email,
            "phone_number": self.phone_number,
            "username": self.username,
            "password": self.password,
        }


@dataclass(frozen=True)
class SignupResultDTO:
    message: str
    user: UserDTO
    verification_token: str
    email_sent: bool
    # "email" when a real email was sent, "console" when the server printed the link to its log.
    email_delivery: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "SignupResultDTO":
        return cls(
            message=data.get("message", ""),
            user=UserDTO.from_api(data["user"]),
            verification_token=data["verification_token"],
            email_sent=bool(data.get("email_sent", False)),
            email_delivery=data.get("email_delivery", "email"),
        )


@dataclass(frozen=True)
class VerificationStatusDTO:
    email_verified: bool
    is_verified: bool
    email: str | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "VerificationStatusDTO":
        return cls(
            email_verified=bool(data.get("email_verified")),
            is_verified=bool(data.get("is_verified")),
            email=data.get("email"),
        )


@dataclass(frozen=True)
class GoogleSignInDTO:
    """An in-progress Google sign-in: open ``authorization_url`` and poll with ``session_id``."""

    session_id: str
    authorization_url: str
    expires_in: int
    poll_interval: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "GoogleSignInDTO":
        return cls(
            session_id=data["session_id"],
            authorization_url=data["authorization_url"],
            expires_in=int(data.get("expires_in", 600)),
            poll_interval=max(1, int(data.get("poll_interval", 2))),
        )


@dataclass(frozen=True)
class UserPageDTO:
    """One page of the admin user list."""

    total: int
    items: list[UserDTO]
    skip: int
    limit: int

    @property
    def page(self) -> int:
        return self.skip // self.limit + 1 if self.limit else 1

    @property
    def page_count(self) -> int:
        return max(1, -(-self.total // self.limit)) if self.limit else 1
