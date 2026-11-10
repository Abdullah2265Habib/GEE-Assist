"""Signs this computer in to Google Earth Engine through the browser.

This is what ``earthengine authenticate`` does in its "localhost" mode, so the app can
do it without a command prompt (gkonsol's ``gee login``):

1. ``begin`` starts a small web server on this computer and returns the Google sign-in
   page to open in the browser;
2. ``wait`` waits for Google to send the browser back to that server with an
   authorization code, exchanges the code for a refresh token and saves it where the
   Earth Engine library looks for it (``~/.config/earthengine/credentials``).

The library's public helpers build the sign-in address, exchange the code and write the
credentials file. The waiting is done here so that it can be cancelled and gives up
after ``timeout`` seconds, instead of waiting forever.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import os
import threading
import time
import urllib.parse
from typing import Any, Callable, Optional

from backend.exceptions import GEEError, GEESetupError

SIGN_IN_TIMEOUT = 300.0   # seconds to wait for the browser to come back
POLL_SECONDS = 0.5        # how often the wait looks for a cancellation
REQUEST_TIMEOUT = 10      # seconds a browser connection may take to send its request


class GEESignInCancelled(GEEError):
    """The sign-in was cancelled before the browser came back."""


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Receives Google's redirect: ``/?code=...`` when signed in, ``/?error=...`` when not."""

    timeout = REQUEST_TIMEOUT

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        server: _CallbackServer = self.server  # type: ignore[assignment]
        if "code" in query:
            server.code = query["code"][0]
            self._reply(200, "Signed in to Google Earth Engine. You can close this tab and return to GEE-Assist.")
        elif "error" in query:
            server.error = query["error"][0]
            self._reply(200, f"The Google Earth Engine sign-in was not completed ({server.error}). "
                             "You can close this tab.")
        else:  # e.g. the browser asking for a favicon
            self._reply(404, "Not found.")

    def _reply(self, status: int, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: Any) -> None:
        pass  # no request log on stderr


class _CallbackServer(http.server.HTTPServer):
    """One sign-in attempt: the web server Google sends the browser back to, and its state."""

    def __init__(self, verifier: str) -> None:
        super().__init__(("localhost", 0), _CallbackHandler)  # any free port
        self.timeout = POLL_SECONDS  # handle_request() returns after this long without a request
        self.verifier = verifier
        self.code: Optional[str] = None
        self.error: Optional[str] = None
        self.cancelled = threading.Event()
        self.waiting = False

    @property
    def url(self) -> str:
        return f"http://localhost:{self.server_address[1]}"


def _pkce_pair() -> tuple[str, str]:
    """A PKCE code verifier and its challenge (RFC 7636): the code only works with our verifier."""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class GEESignIn:
    """Browser sign-in: ``begin``, then ``wait`` (or ``cancel``). A new ``begin`` cancels the last one."""

    def __init__(
        self,
        oauth: Any = None,
        timeout: float = SIGN_IN_TIMEOUT,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._oauth = oauth  # ``ee.oauth``, imported when first needed; tests pass a fake
        self._timeout = timeout
        self._clock = clock
        self._lock = threading.Lock()
        self._attempt: Optional[_CallbackServer] = None

    def begin(self) -> str:
        """Start waiting for the browser. Returns the Google sign-in page to open."""
        oauth = self._load()
        self.cancel()  # an earlier sign-in that was never finished
        verifier, challenge = _pkce_pair()
        attempt = _CallbackServer(verifier)
        try:
            url = oauth.get_authorization_url(challenge, list(oauth.SCOPES), attempt.url)
        except Exception as exc:
            attempt.server_close()
            raise GEESetupError(f"Could not start the Earth Engine sign-in: {exc}") from exc
        with self._lock:
            self._attempt = attempt
        return url

    def wait(self, should_stop: Optional[Callable[[], bool]] = None) -> str:
        """Wait for the browser, then save the credentials. Returns the file they were saved in.

        Raises:
            GEESignInCancelled: ``should_stop`` returned True or ``cancel`` was called.
            GEESetupError: Google refused the sign-in, the browser did not come back in
                time, or the credentials could not be saved.
        """
        with self._lock:
            attempt = self._attempt
            if attempt is None:
                raise GEEError("Start the Earth Engine sign-in first.")
            attempt.waiting = True
        stop = should_stop or (lambda: False)
        deadline = self._clock() + self._timeout
        try:
            while attempt.code is None and attempt.error is None:
                if stop() or attempt.cancelled.is_set():
                    raise GEESignInCancelled("The Earth Engine sign-in was cancelled.")
                if self._clock() >= deadline:
                    raise GEESetupError(
                        f"The browser did not come back within {self._timeout / 60:.0f} minutes. "
                        "Start the sign-in again."
                    )
                try:
                    attempt.handle_request()
                except OSError as exc:
                    raise GEESetupError(f"The Earth Engine sign-in stopped: {exc}") from exc
        finally:
            with self._lock:
                attempt.waiting = False
                if self._attempt is attempt:
                    self._attempt = None
            attempt.server_close()
        if attempt.error:
            raise GEESetupError(f"Google did not sign you in to Earth Engine ({attempt.error}).")
        return self._save(attempt.code or "", attempt.verifier, attempt.url)

    def cancel(self) -> None:
        """Stop the sign-in that is waiting, or was begun and never waited for."""
        with self._lock:
            attempt, self._attempt = self._attempt, None
            if attempt is None:
                return
            attempt.cancelled.set()
            if attempt.waiting:
                return  # the wait sees the cancellation within POLL_SECONDS and closes the server
        attempt.server_close()

    # ------------------------------------------------------------- helpers
    def _save(self, code: str, verifier: str, redirect_uri: str) -> str:
        oauth = self._load()
        try:
            token = oauth.request_token(code, verifier, redirect_uri=redirect_uri)
            path = oauth.get_credentials_path()
            # The same file ``earthengine authenticate`` writes.
            oauth.write_private_json(path, {
                "redirect_uri": redirect_uri, "refresh_token": token, "scopes": list(oauth.SCOPES),
            })
        except Exception as exc:
            raise GEESetupError(f"Could not save the Earth Engine sign-in: {exc}") from exc
        return path

    def _load(self) -> Any:
        if self._oauth is None:
            try:
                from ee import oauth
            except ImportError as exc:
                raise GEESetupError("The Earth Engine library is missing: pip install earthengine-api") from exc
            self._oauth = oauth
        return self._oauth
