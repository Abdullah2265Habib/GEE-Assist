import httpx
import pytest

from backend import auth_exceptions as errors
from backend.data.clients.auth_api_client import AuthApiClient


def _client(handler) -> AuthApiClient:
    return AuthApiClient("http://auth.test", transport=httpx.MockTransport(handler))


def _respond(status: int, body=None, headers=None):
    return lambda request: httpx.Response(status, json=body, headers=headers)


def test_login_sends_credentials_and_returns_body():
    seen = {}

    def handler(request: httpx.Request):
        seen["path"] = request.url.path
        seen["body"] = request.content
        return httpx.Response(200, json={"access_token": "a"})

    assert _client(handler).login("abdullah", "secret123") == {"access_token": "a"}
    assert seen["path"] == "/auth/login"
    assert b'"username":"abdullah"' in seen["body"].replace(b" ", b"")


def test_bearer_token_is_sent():
    def handler(request: httpx.Request):
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json={"id": "1"})

    _client(handler).me("tok")


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (401, {"detail": "Invalid token"}, errors.SessionExpiredError),
        (403, {"detail": "Account is disabled"}, errors.AccountDisabledError),
        (403, {"detail": "You do not have permission to perform this action"}, errors.PermissionDeniedError),
        (404, {"detail": "User not found"}, errors.NotFoundError),
        (400, {"detail": "You cannot change your own role"}, errors.InvalidRequestError),
        (502, {"detail": "Could not send"}, errors.EmailDeliveryError),
        (503, {"detail": "Google sign-in is not configured"}, errors.GoogleSignInUnavailableError),
        (500, None, errors.AuthError),
    ],
)
def test_status_codes_map_to_errors(status, body, expected):
    with pytest.raises(expected):
        _client(_respond(status, body)).me("tok")


def test_wrong_password_is_invalid_credentials():
    with pytest.raises(errors.InvalidCredentialsError, match="Invalid username or password"):
        _client(_respond(401, {"detail": "Invalid username or password"})).login("a", "b")


def test_verification_required_carries_token():
    body = {"detail": {"code": "VERIFICATION_REQUIRED", "message": "Verify first",
                       "email_verified": False, "verification_token": "vt"}}
    with pytest.raises(errors.VerificationRequiredError) as info:
        _client(_respond(403, body)).login("a", "b")
    assert info.value.verification_token == "vt"


@pytest.mark.parametrize(
    ("message", "field"),
    [("Username is already taken", "username"),
     ("Email is already registered", "email"),
     ("Phone number is already registered", "phone_number")],
)
def test_conflict_names_the_field(message, field):
    with pytest.raises(errors.ConflictError) as info:
        _client(_respond(409, {"detail": message})).signup({})
    assert info.value.field == field


def test_validation_errors_are_mapped_per_field():
    body = {"detail": [
        {"loc": ["body", "password"], "msg": "String should have at least 8 characters"},
        {"loc": ["body", "phone_number"], "msg": "Value error, Phone number must be in international format"},
    ]}
    with pytest.raises(errors.FieldValidationError) as info:
        _client(_respond(422, body)).signup({})
    assert info.value.field_errors == {
        "password": "Must be at least 8 characters",
        "phone_number": "Phone number must be in international format",
    }


def test_rate_limit_reads_retry_after():
    with pytest.raises(errors.RateLimitedError) as info:
        _client(_respond(429, {"detail": "wait"}, {"Retry-After": "42"})).resend_verification_email("vt")
    assert info.value.retry_after == 42


def test_google_poll_pending_returns_none():
    assert _client(_respond(202, {"status": "pending"})).google_poll("session-id-123") is None


def test_google_poll_cancelled_is_not_session_expired():
    with pytest.raises(errors.AuthError) as info:
        _client(_respond(401, {"detail": "Google sign-in was cancelled"})).google_poll("session-id-123")
    assert not isinstance(info.value, errors.SessionExpiredError)


def test_unreachable_server():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(errors.ServerUnavailableError):
        _client(handler).login("a", "b")
    assert _client(handler).health() is False
