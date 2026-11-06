"""httpx implementation of IAuthApiClient. Translates HTTP errors into ``AuthError`` subclasses."""

from __future__ import annotations

import re
from typing import Any

import httpx

from backend.auth_exceptions import (
    AccountDisabledError,
    AuthError,
    ConflictError,
    EmailDeliveryError,
    FieldValidationError,
    GoogleSignInUnavailableError,
    InvalidCredentialsError,
    InvalidRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    ServerUnavailableError,
    SessionExpiredError,
    VerificationRequiredError,
)
from backend.data.clients.i_auth_api_client import IAuthApiClient

_CONFLICT_FIELDS = (("username", "username"), ("email", "email"), ("phone", "phone_number"))


class AuthApiClient(IAuthApiClient):
    def __init__(self, base_url: str, timeout: float = 15.0, transport: httpx.BaseTransport | None = None):
        self._base_url = base_url.rstrip("/")
        # httpx.Client is thread-safe, so one client is shared by all background workers.
        self._http = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": "GEE-Assist-Desktop"},
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------ public
    def health(self) -> bool:
        try:
            response = self._http.get("/health", timeout=5)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def signup(self, payload: dict[str, str]) -> dict[str, Any]:
        return self._request("POST", "/auth/signup", json=payload)

    def login(self, username: str, password: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/auth/login",
            json={"username": username, "password": password},
            unauthorized=InvalidCredentialsError,
        )

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        return self._request("POST", "/auth/refresh", json={"refresh_token": refresh_token})

    def me(self, access_token: str) -> dict[str, Any]:
        return self._request("GET", "/auth/me", token=access_token)

    # ------------------------------------------------------------ verification
    def verification_status(self, verification_token: str) -> dict[str, Any]:
        return self._request("GET", "/auth/verification-status", token=verification_token)

    def resend_verification_email(self, verification_token: str, email: str | None = None) -> dict[str, Any]:
        body = {"email": email} if email else {}
        return self._request("POST", "/auth/verify-email/resend", token=verification_token, json=body)

    # ------------------------------------------------------------------ Google
    def google_start(self) -> dict[str, Any]:
        return self._request("POST", "/auth/google/start")

    def google_poll(self, session_id: str) -> dict[str, Any] | None:
        response = self._send("POST", "/auth/google/poll", json={"session_id": session_id})
        if response.status_code == 202:
            return None
        # A 401 here means the user cancelled at Google, not that a token expired.
        _raise_for_status(response, unauthorized=AuthError)
        return response.json()

    # ------------------------------------------------------------------- admin
    def list_users(self, access_token: str, skip: int = 0, limit: int = 50) -> dict[str, Any]:
        return self._request("GET", "/admin/users", token=access_token, params={"skip": skip, "limit": limit})

    def get_user(self, access_token: str, user_id: str) -> dict[str, Any]:
        return self._request("GET", f"/admin/users/{user_id}", token=access_token)

    def update_user_role(self, access_token: str, user_id: str, role: str) -> dict[str, Any]:
        return self._request("PATCH", f"/admin/users/{user_id}/role", token=access_token, json={"role": role})

    def update_user_status(self, access_token: str, user_id: str, is_active: bool) -> dict[str, Any]:
        return self._request(
            "PATCH", f"/admin/users/{user_id}/status", token=access_token, json={"is_active": is_active}
        )

    # ----------------------------------------------------------------- helpers
    def _send(self, method: str, path: str, *, token: str | None = None, **kwargs: Any) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else None
        try:
            return self._http.request(method, path, headers=headers, **kwargs)
        except httpx.TimeoutException as exc:
            raise ServerUnavailableError("The server took too long to respond. Please try again.") from exc
        except httpx.HTTPError as exc:
            raise ServerUnavailableError(
                f"Cannot reach the GEE-Assist server at {self._base_url}. "
                "Check your internet connection or try again later."
            ) from exc

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        unauthorized: type[AuthError] = SessionExpiredError,
        **kwargs: Any,
    ) -> dict[str, Any]:
        response = self._send(method, path, token=token, **kwargs)
        _raise_for_status(response, unauthorized=unauthorized)
        try:
            return response.json()
        except ValueError as exc:
            raise AuthError("The server sent an unexpected response.", response.status_code) from exc


# --------------------------------------------------------------------------- error mapping

def _detail(response: httpx.Response) -> Any:
    try:
        return response.json().get("detail")
    except (ValueError, AttributeError):
        return None


def _raise_for_status(response: httpx.Response, *, unauthorized: type[AuthError]) -> None:
    code = response.status_code
    if code < 400:
        return
    detail = _detail(response)
    message = detail if isinstance(detail, str) else ""

    if code == 401:
        raise unauthorized(message or "Your session has expired. Please sign in again.", code)
    if code == 403:
        if isinstance(detail, dict) and detail.get("code") == "VERIFICATION_REQUIRED":
            raise VerificationRequiredError(
                detail.get("message") or "Please verify your email address before signing in.",
                verification_token=detail["verification_token"],
                email_verified=bool(detail.get("email_verified")),
            )
        if "disabled" in message.lower():
            raise AccountDisabledError("This account has been disabled. Contact an administrator.", code)
        raise PermissionDeniedError(message or "You are not allowed to do this.", code)
    if code == 404:
        raise NotFoundError(message or "Not found.", code)
    if code == 409:
        lowered = message.lower()
        field = next((f for word, f in _CONFLICT_FIELDS if word in lowered), None)
        raise ConflictError(message or "This already exists.", field)
    if code == 422:
        field_errors = _parse_validation_errors(detail)
        summary = next(iter(field_errors.values()), "Some fields are not valid.")
        raise FieldValidationError(summary, field_errors)
    if code == 429:
        retry_after = _int(response.headers.get("Retry-After"), 60)
        raise RateLimitedError(message or f"Please wait {retry_after} seconds and try again.", retry_after)
    if code == 400:
        raise InvalidRequestError(message or "The request was not valid.", code)
    if code == 502:
        raise EmailDeliveryError(message or "The email could not be sent. Try again later.", code)
    if code == 503:
        raise GoogleSignInUnavailableError(message or "This service is not available right now.", code)
    raise AuthError(message or f"The server had a problem (error {code}). Please try again later.", code)


def _parse_validation_errors(detail: Any) -> dict[str, str]:
    """FastAPI 422 detail -> {"field": "readable message"}."""
    errors: dict[str, str] = {}
    if not isinstance(detail, list):
        return errors
    for item in detail:
        if not isinstance(item, dict):
            continue
        loc = item.get("loc") or []
        field = str(loc[-1]) if loc else "form"
        errors.setdefault(field, _readable(str(item.get("msg", "Invalid value"))))
    return errors


def _readable(msg: str) -> str:
    msg = re.sub(r"^Value error,\s*", "", msg)
    msg = msg.replace("value is not a valid email address: ", "")
    msg = re.sub(r"^String should have at least (\d+) characters?$", r"Must be at least \1 characters", msg)
    msg = re.sub(r"^String should have at most (\d+) characters?$", r"Must be at most \1 characters", msg)
    return msg[:1].upper() + msg[1:]


def _int(value: str | None, default: int) -> int:
    try:
        return max(1, int(value)) if value is not None else default
    except ValueError:
        return default
