import time

import pytest

from backend.auth_exceptions import AccountDisabledError, AuthError, ServerUnavailableError, SessionExpiredError
from backend.business.user import UserService
from backend.data.session_store import MemorySessionStore

USER = {"id": "u1", "username": "abdullah", "full_name": "Abdullah Habib", "role": "user",
        "is_active": True, "email": "a@example.com", "email_verified": True,
        "created_at": "2026-11-03T06:06:09Z"}


def _login_response(n=1):
    return {"access_token": f"access{n}", "refresh_token": f"refresh{n}", "expires_in": 1800, "user": USER}


class FakeApi:
    def __init__(self):
        self.calls = []
        self.reject_access = set()
        self.refresh_error = None
        self.refresh_count = 0

    def health(self):
        return True

    def login(self, username, password):
        self.calls.append(("login", username))
        return _login_response()

    def refresh(self, refresh_token):
        self.calls.append(("refresh", refresh_token))
        if self.refresh_error:
            raise self.refresh_error
        self.refresh_count += 1
        n = self.refresh_count + 1
        return {"access_token": f"access{n}", "refresh_token": f"refresh{n}", "expires_in": 1800}

    def me(self, token):
        self.calls.append(("me", token))
        if token in self.reject_access:
            raise SessionExpiredError("Token has expired", 401)
        return USER

    def list_users(self, token, skip, limit):
        if token in self.reject_access:
            raise SessionExpiredError("Token has expired", 401)
        return {"total": 1, "items": [USER]}

    def google_poll(self, session_id):
        return None if session_id == "pending" else _login_response()


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _save_session(store, expires_in=3600.0):
    """A session saved by an earlier "Keep me signed in" that has not run out yet."""
    store.save_refresh_token("refresh1")
    store.save_expiry(time.time() + expires_in)


@pytest.fixture
def setup():
    api, store, clock = FakeApi(), MemorySessionStore(), Clock()
    return UserService(api, store, clock), api, store, clock


def test_login_normalises_username_and_sets_current_user(setup):
    service, api, store, _ = setup
    user = service.log_in("  Abdullah ", "secret123")
    assert api.calls[0] == ("login", "abdullah")
    assert user.username == "abdullah" and service.current_user == user
    assert store.load_refresh_token() is None  # not remembered


def test_login_requires_both_fields(setup):
    service, *_ = setup
    with pytest.raises(AuthError):
        service.log_in("", "x")


def test_remember_me_saves_refresh_token(setup):
    service, _, store, _ = setup
    service.log_in("abdullah", "secret123", remember=True)
    assert store.load_refresh_token() == "refresh1"


def test_expired_access_token_is_refreshed_before_the_call(setup):
    service, api, _, clock = setup
    service.log_in("abdullah", "secret123")
    clock.now += 1800  # past expiry
    service.reload_current_user()
    assert ("refresh", "refresh1") in api.calls
    assert api.calls[-1] == ("me", "access2")


def test_rejected_access_token_is_refreshed_once(setup):
    service, api, _, _ = setup
    service.log_in("abdullah", "secret123")
    api.reject_access.add("access1")
    page = service.list_users()
    assert page.total == 1 and api.refresh_count == 1


def test_failed_refresh_logs_out(setup):
    service, api, store, _ = setup
    service.log_in("abdullah", "secret123", remember=True)
    api.reject_access.add("access1")
    api.refresh_error = SessionExpiredError("expired", 401)
    with pytest.raises(SessionExpiredError):
        service.reload_current_user()
    assert service.current_user is None and store.load_refresh_token() is None


def test_restore_session_uses_saved_refresh_token(setup):
    service, _, store, _ = setup
    _save_session(store)
    user = service.restore_session()
    assert user.username == "abdullah"
    assert store.load_refresh_token() == "refresh2"  # the new refresh token is saved


def test_restore_session_without_saved_token(setup):
    service, *_ = setup
    assert service.restore_session() is None


@pytest.mark.parametrize("error", [SessionExpiredError("x", 401), AccountDisabledError("x", 403)])
def test_restore_session_forgets_rejected_token(setup, error):
    service, api, store, _ = setup
    _save_session(store)
    api.refresh_error = error
    assert service.restore_session() is None
    assert store.load_refresh_token() is None


def test_restore_session_keeps_token_when_offline(setup):
    service, api, store, _ = setup
    _save_session(store)
    api.refresh_error = ServerUnavailableError("offline")
    with pytest.raises(ServerUnavailableError):
        service.restore_session()
    assert store.load_refresh_token() == "refresh1"


def test_google_poll(setup):
    service, *_ = setup
    assert service.poll_google_sign_in("pending") is None
    assert service.poll_google_sign_in("done").username == "abdullah"


def test_log_out_clears_everything(setup):
    service, _, store, _ = setup
    service.log_in("abdullah", "secret123", remember=True)
    service.log_out()
    assert service.current_user is None and store.load_refresh_token() is None


def test_invalid_role_is_rejected(setup):
    service, *_ = setup
    service.log_in("abdullah", "secret123")
    with pytest.raises(AuthError):
        service.set_user_role("u2", "superuser")


# ------------------------------------------------------------- "keep me signed in" duration
SESSION = 120.0  # two minutes


@pytest.fixture
def timed():
    """A service whose saved sessions last SESSION seconds, with a controllable wall clock."""
    api, store, wall = FakeApi(), MemorySessionStore(), Clock()
    wall.now = 1_700_000_000.0
    service = UserService(api, store, Clock(), session_duration=SESSION, wall_clock=wall)
    return service, store, wall


def test_remembered_login_saves_when_the_session_runs_out(timed):
    service, store, wall = timed
    service.log_in("abdullah", "secret123", remember=True)
    assert store.load_expiry() == wall.now + SESSION


def test_login_without_remember_saves_no_expiry(timed):
    service, store, _ = timed
    service.log_in("abdullah", "secret123")
    assert store.load_expiry() is None


def test_session_is_restored_before_it_runs_out(timed):
    service, store, wall = timed
    service.log_in("abdullah", "secret123", remember=True)
    wall.now += SESSION - 1
    assert service.restore_session().username == "abdullah"


def test_session_that_ran_out_needs_a_new_sign_in(timed):
    service, store, wall = timed
    service.log_in("abdullah", "secret123", remember=True)
    wall.now += SESSION
    assert service.restore_session() is None
    assert store.load_refresh_token() is None and store.load_expiry() is None


def test_restoring_does_not_extend_the_session(timed):
    service, store, wall = timed
    service.log_in("abdullah", "secret123", remember=True)
    expires_at = store.load_expiry()
    wall.now += 60
    service.restore_session()
    assert store.load_expiry() == expires_at


def test_saved_session_without_expiry_needs_a_new_sign_in(timed):
    service, store, _ = timed
    store.save_refresh_token("refresh1")  # saved before sessions had a time limit
    assert service.restore_session() is None
    assert store.load_refresh_token() is None
