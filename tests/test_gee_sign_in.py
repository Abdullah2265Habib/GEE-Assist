"""Signing this computer in to Earth Engine through the browser (gkonsol's ``gee login``)."""

from __future__ import annotations

import base64
import hashlib
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from backend.data.clients import gee_sign_in
from backend.data.clients.gee_sign_in import GEESignIn, GEESignInCancelled
from backend.exceptions import GEEError, GEESetupError


class FakeOAuth:
    """Stands in for ``ee.oauth``: no Google servers are contacted."""

    SCOPES = ("https://www.googleapis.com/auth/earthengine",)

    def __init__(self, folder):
        self.path = str(folder / "credentials")
        self.redirect_uri = self.challenge = None
        self.exchanged = self.saved = None

    def get_authorization_url(self, challenge, scopes, redirect_uri):
        self.challenge, self.redirect_uri = challenge, redirect_uri
        return "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode({"redirect_uri": redirect_uri})

    def request_token(self, code, verifier, redirect_uri=None):
        self.exchanged = (code, verifier, redirect_uri)
        return "refresh-token-1"

    def get_credentials_path(self):
        return self.path

    def write_private_json(self, path, info):
        self.saved = (path, info)


def _ipv4(url: str) -> str:
    """The server listens on 127.0.0.1; asking "localhost" makes Windows try ::1 first, which is slow."""
    return url.replace("//localhost:", "//127.0.0.1:")


def _browser_returns(url: str) -> threading.Thread:
    """The browser following Google's redirect back to the app (the server answers once it is waited on)."""
    def visit():
        try:
            urllib.request.urlopen(_ipv4(url), timeout=10).read()
        except urllib.error.HTTPError:
            pass
    thread = threading.Thread(target=visit, daemon=True)
    thread.start()
    return thread


@pytest.fixture
def oauth(tmp_path, monkeypatch):
    monkeypatch.setattr(gee_sign_in, "POLL_SECONDS", 0.02)  # look for cancellations often: quick tests
    return FakeOAuth(tmp_path)


def test_begin_returns_the_google_page_that_comes_back_to_this_computer(oauth):
    sign_in = GEESignIn(oauth)
    url = sign_in.begin()
    assert url.startswith("https://accounts.google.com/")
    assert oauth.redirect_uri.startswith("http://localhost:")
    sign_in.cancel()


def test_the_code_from_the_browser_is_saved_as_credentials(oauth):
    sign_in = GEESignIn(oauth)
    sign_in.begin()
    browser = _browser_returns(oauth.redirect_uri + "/?code=4%2Fabc&scope=earthengine")

    path = sign_in.wait()
    browser.join(5)

    code, verifier, redirect_uri = oauth.exchanged
    assert code == "4/abc" and redirect_uri == oauth.redirect_uri
    # PKCE: the code only works with the verifier whose challenge was sent to Google.
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == oauth.challenge
    assert path == oauth.path
    assert oauth.saved == (oauth.path, {"redirect_uri": oauth.redirect_uri, "refresh_token": "refresh-token-1",
                                        "scopes": list(FakeOAuth.SCOPES)})


def test_other_requests_are_ignored_until_the_code_arrives(oauth):
    sign_in = GEESignIn(oauth)
    sign_in.begin()
    result = {}
    waiter = threading.Thread(target=lambda: result.update(path=sign_in.wait()), daemon=True)
    waiter.start()

    with pytest.raises(urllib.error.HTTPError) as not_found:
        urllib.request.urlopen(_ipv4(oauth.redirect_uri) + "/favicon.ico", timeout=10)
    assert not_found.value.code == 404 and waiter.is_alive()  # still waiting for the code
    urllib.request.urlopen(_ipv4(oauth.redirect_uri) + "/?code=xyz", timeout=10).read()
    waiter.join(5)
    assert result["path"] == oauth.path and oauth.exchanged[0] == "xyz"


def test_a_refused_sign_in_is_reported(oauth):
    sign_in = GEESignIn(oauth)
    sign_in.begin()
    _browser_returns(oauth.redirect_uri + "/?error=access_denied")
    with pytest.raises(GEESetupError, match="access_denied"):
        sign_in.wait()
    assert oauth.saved is None


def test_waiting_stops_when_asked(oauth):
    sign_in = GEESignIn(oauth)
    sign_in.begin()
    with pytest.raises(GEESignInCancelled):
        sign_in.wait(should_stop=lambda: True)


def test_waiting_gives_up_after_the_timeout(oauth):
    now = [0.0]

    def clock():
        now[0] += 100.0  # every look at the clock is 100 s later
        return now[0]

    sign_in = GEESignIn(oauth, timeout=250.0, clock=clock)
    sign_in.begin()
    with pytest.raises(GEESetupError, match="did not come back"):
        sign_in.wait()


def test_cancel_stops_a_wait_in_another_thread(oauth):
    sign_in = GEESignIn(oauth)
    sign_in.begin()
    errors, waiter = _wait_in_background(sign_in)

    sign_in.cancel()
    waiter.join(5)
    assert not waiter.is_alive() and isinstance(errors[0], GEESignInCancelled)


def test_a_new_sign_in_cancels_the_unfinished_one(oauth):
    sign_in = GEESignIn(oauth)
    sign_in.begin()
    first = oauth.redirect_uri
    errors, waiter = _wait_in_background(sign_in)

    sign_in.begin()
    waiter.join(5)
    assert isinstance(errors[0], GEESignInCancelled)
    assert oauth.redirect_uri != first  # the new attempt has a server of its own
    sign_in.cancel()


def _wait_in_background(sign_in: GEESignIn) -> tuple[list, threading.Thread]:
    """Run ``wait`` in a thread; return once it is waiting (it has asked whether to stop)."""
    errors: list = []
    waiting = threading.Event()

    def should_stop() -> bool:
        waiting.set()
        return False

    def wait() -> None:
        try:
            sign_in.wait(should_stop)
        except GEEError as exc:
            errors.append(exc)

    waiter = threading.Thread(target=wait, daemon=True)
    waiter.start()
    assert waiting.wait(5)
    return errors, waiter


def test_wait_needs_a_sign_in_to_be_begun(oauth):
    with pytest.raises(GEEError, match="first"):
        GEESignIn(oauth).wait()
