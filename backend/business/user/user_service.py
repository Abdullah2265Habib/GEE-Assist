"""Class diagram: UserService. Desktop-side authentication logic on top of the auth server."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, TypeVar

from backend.auth_exceptions import AuthError, SessionExpiredError
from backend.business.user.i_user_service import IUserService
from backend.data.clients.i_auth_api_client import IAuthApiClient
from backend.data.session_store import ISessionStore
from backend.dto.user_dto import (
    GoogleSignInDTO,
    SignupDTO,
    SignupResultDTO,
    UserDTO,
    UserPageDTO,
    VerificationStatusDTO,
)

T = TypeVar("T")

# Refresh the access token this many seconds before it really expires.
_EXPIRY_MARGIN_SECONDS = 30
# Default length of a "Keep me signed in" session (SESSION_DURATION in .env).
DEFAULT_SESSION_DURATION = 7 * 24 * 3600


class UserService(IUserService):
    def __init__(
        self,
        api: IAuthApiClient,
        session_store: ISessionStore,
        clock: Callable[[], float] = time.monotonic,
        session_duration: float = DEFAULT_SESSION_DURATION,
        wall_clock: Callable[[], float] = time.time,
    ):
        """``clock`` times access tokens within this run; ``wall_clock`` (seconds since the
        epoch) times the saved session across launches, which lasts ``session_duration`` seconds."""
        self._api = api
        self._store = session_store
        self._clock = clock
        self._session_duration = session_duration
        self._wall_clock = wall_clock
        self._lock = threading.RLock()  # workers may call the service from several threads

        self._user: UserDTO | None = None
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._access_expires_at = 0.0
        self._remember = False

    # ------------------------------------------------------------- server
    def is_server_available(self) -> bool:
        return self._api.health()

    # ------------------------------------------------------------- session
    @property
    def current_user(self) -> UserDTO | None:
        return self._user

    def log_in(self, username: str, password: str, remember: bool = False) -> UserDTO:
        username = username.strip().lower()
        if not username or not password:
            raise AuthError("Enter your username and password.")
        return self._start_session(self._api.login(username, password), remember)

    def restore_session(self) -> UserDTO | None:
        refresh_token = self._store.load_refresh_token()
        if not refresh_token:
            return None
        expires_at = self._store.load_expiry()
        if expires_at is None or self._wall_clock() >= expires_at:
            self._store.clear()  # "Keep me signed in" has run out: sign in again
            return None
        try:
            tokens = self._api.refresh(refresh_token)
            user = UserDTO.from_api(self._api.me(tokens["access_token"]))
        except SessionExpiredError:
            self._store.clear()
            return None
        except AuthError as exc:
            # Disabled or no longer verified: forget the saved session. Network errors keep it.
            if exc.status_code in (401, 403):
                self._store.clear()
                return None
            raise
        with self._lock:
            self._set_tokens(tokens, remember=True)
            self._user = user
        return user

    def reload_current_user(self) -> UserDTO:
        user = UserDTO.from_api(self._authorized(self._api.me))
        self._user = user
        return user

    def log_out(self) -> None:
        with self._lock:
            self._user = None
            self._access_token = None
            self._refresh_token = None
            self._access_expires_at = 0.0
            self._remember = False
        self._store.clear()

    # ------------------------------------------------------------- sign-up / verification
    def sign_up(self, data: SignupDTO) -> SignupResultDTO:
        return SignupResultDTO.from_api(self._api.signup(data.to_api()))

    def get_verification_status(self, verification_token: str) -> VerificationStatusDTO:
        return VerificationStatusDTO.from_api(self._api.verification_status(verification_token))

    def resend_verification_email(self, verification_token: str, new_email: str | None = None) -> str:
        new_email = (new_email or "").strip().lower() or None
        return self._api.resend_verification_email(verification_token, new_email).get("message", "Email sent.")

    # ------------------------------------------------------------- Google
    def start_google_sign_in(self) -> GoogleSignInDTO:
        return GoogleSignInDTO.from_api(self._api.google_start())

    def poll_google_sign_in(self, session_id: str, remember: bool = False) -> UserDTO | None:
        result = self._api.google_poll(session_id)
        if result is None:
            return None
        return self._start_session(result, remember)

    # ------------------------------------------------------------- admin
    def list_users(self, skip: int = 0, limit: int = 50) -> UserPageDTO:
        data = self._authorized(lambda token: self._api.list_users(token, skip, limit))
        return UserPageDTO(
            total=int(data.get("total", 0)),
            items=[UserDTO.from_api(item) for item in data.get("items", [])],
            skip=skip,
            limit=limit,
        )

    def get_user(self, user_id: str) -> UserDTO:
        return UserDTO.from_api(self._authorized(lambda token: self._api.get_user(token, user_id)))

    def set_user_role(self, user_id: str, role: str) -> UserDTO:
        if role not in ("admin", "user"):
            raise AuthError(f"Unknown role '{role}'.")
        return UserDTO.from_api(self._authorized(lambda token: self._api.update_user_role(token, user_id, role)))

    def set_user_active(self, user_id: str, is_active: bool) -> UserDTO:
        return UserDTO.from_api(
            self._authorized(lambda token: self._api.update_user_status(token, user_id, is_active))
        )

    # ------------------------------------------------------------- helpers
    def _start_session(self, login_response: dict[str, Any], remember: bool) -> UserDTO:
        user = UserDTO.from_api(login_response["user"])
        with self._lock:
            self._set_tokens(login_response, remember)
            self._user = user
        if remember:
            # Counted from this sign-in; refreshing tokens later does not extend it.
            self._store.save_expiry(self._wall_clock() + self._session_duration)
        else:
            self._store.clear()  # don't keep a session saved by an earlier "Keep me signed in"
        return user

    def _set_tokens(self, tokens: dict[str, Any], remember: bool) -> None:
        self._access_token = tokens["access_token"]
        self._refresh_token = tokens.get("refresh_token") or self._refresh_token
        self._access_expires_at = self._clock() + int(tokens.get("expires_in", 0)) - _EXPIRY_MARGIN_SECONDS
        self._remember = remember
        if remember and self._refresh_token:
            self._store.save_refresh_token(self._refresh_token)

    def _refresh_access_token(self) -> str:
        with self._lock:
            if not self._refresh_token:
                raise SessionExpiredError("You are not signed in.", 401)
            try:
                tokens = self._api.refresh(self._refresh_token)
            except SessionExpiredError:
                self.log_out()
                raise
            self._set_tokens(tokens, self._remember)
            return self._access_token

    def _valid_access_token(self) -> str:
        with self._lock:
            if self._access_token and self._clock() < self._access_expires_at:
                return self._access_token
        return self._refresh_access_token()

    def _authorized(self, call: Callable[[str], T]) -> T:
        """Run an API call with a valid access token, refreshing it once if the server rejects it."""
        try:
            return call(self._valid_access_token())
        except SessionExpiredError:
            if not self._refresh_token:
                raise
            return call(self._refresh_access_token())
