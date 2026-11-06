"""Drives the sign-in UI against an in-memory fake facade (no server, no window on screen)."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication  # noqa: E402

from backend.auth_exceptions import ConflictError, InvalidCredentialsError, VerificationRequiredError  # noqa: E402
from backend.dto.user_dto import SignupResultDTO, UserDTO, VerificationStatusDTO  # noqa: E402

USER = UserDTO(id="u1", username="abdullah", full_name="Abdullah Habib", role="user", email="a@example.com",
               email_verified=True)


class FakeFacade:
    def __init__(self):
        self.verified = False
        self.saved_session = False
        self.calls = []

    def is_server_available(self):
        return True

    def restore_session(self):
        return USER if self.saved_session else None

    def log_in(self, username, password, remember=False):
        self.calls.append(("log_in", username, remember))
        if password != "StrongPass123":
            raise InvalidCredentialsError("Invalid username or password", 401)
        if not self.verified:
            raise VerificationRequiredError("Please verify your email address", "vtoken")
        return USER

    def get_verification_status(self, token):
        return VerificationStatusDTO(self.verified, self.verified, "a@example.com")

    def resend_verification_email(self, token, new_email=None):
        self.calls.append(("resend", new_email))
        return f"Verification email sent to {new_email or 'a@example.com'}"

    def sign_up(self, data):
        if data.username == "taken":
            raise ConflictError("Username is already taken", "username")
        return SignupResultDTO("Account created.", USER, "vtoken", True, "email")

    def start_google_sign_in(self):
        raise AssertionError("not used")

    def log_out(self):
        pass


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(app):
    from frontend.theme import apply_theme
    from frontend.views.auth import AuthView

    apply_theme(app)
    facade = FakeFacade()
    view = AuthView(facade)
    view.resize(1400, 900)
    view.show()
    signed_in = []
    view.authenticated.connect(signed_in.append)
    yield view, facade, signed_in
    view.close()
    view.deleteLater()


def wait_until(condition, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QApplication.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_empty_login_shows_field_errors(view):
    v, facade, _ = view
    v.login_page._submit()
    assert v.login_page.username.has_error() and v.login_page.password.has_error()
    assert facade.calls == []


def test_wrong_password_shows_banner(view):
    v, _, signed_in = view
    v.login_page.username.set_text("abdullah")
    v.login_page.password.set_text("nope")
    v.login_page._submit()
    assert wait_until(lambda: not v.login_page.banner.isHidden())
    assert "Invalid username or password" in v.login_page.banner.text()
    assert signed_in == []


def test_unverified_login_goes_to_verification_and_signs_in_once_verified(view):
    v, facade, signed_in = view
    v.login_page.username.set_text("abdullah")
    v.login_page.password.set_text("StrongPass123")
    v.login_page.remember.setChecked(True)
    v.login_page._submit()
    assert wait_until(lambda: v.pages.currentWidget() is v.verification_page)
    assert wait_until(lambda: "a@example.com" in v.verification_page.subtitle.text())

    facade.verified = True          # the user opens the email link
    v.verification_page.check_now.click()
    assert wait_until(lambda: signed_in == [USER])
    assert facade.calls[-1] == ("log_in", "abdullah", True)  # "keep me signed in" is kept


def test_change_email_resends(view):
    v, facade, _ = view
    v.verification_page.start("vtoken", "abdullah", "StrongPass123")
    v._switch(v.verification_page)
    v.verification_page._toggle_change_email()
    v.verification_page.new_email.set_text("new@example.com")
    v.verification_page._submit_new_email()
    assert wait_until(lambda: ("resend", "new@example.com") in facade.calls)
    assert wait_until(lambda: "Resend email in" in v.verification_page.resend.text())


def test_signup_validates_then_reports_conflict_on_field(view):
    v, _, _ = view
    v.show_signup()
    page = v.signup_page
    page._submit()
    assert page.full_name.has_error() and page.email.has_error()

    for field, value in ((page.full_name, "Abdullah Habib"), (page.email, "a@example.com"),
                         (page.phone, "+923001234567"), (page.username, "taken"),
                         (page.password, "StrongPass123"), (page.confirm, "StrongPass123")):
        field.set_text(value)
    page._submit()
    assert wait_until(page.username.has_error)
    assert "already taken" in page.username.message.text()


def test_signup_success_opens_verification(view):
    v, _, _ = view
    v.show_signup()
    page = v.signup_page
    for field, value in ((page.full_name, "Abdullah Habib"), (page.email, "a@example.com"),
                         (page.phone, "+92 300 1234567"), (page.username, "abdullah"),
                         (page.password, "StrongPass123"), (page.confirm, "StrongPass123")):
        field.set_text(value)
    page._submit()
    assert wait_until(lambda: v.pages.currentWidget() is v.verification_page)
    assert "Resend email in" in v.verification_page.resend.text()  # signup already sent one


def test_saved_session_signs_in_automatically(view):
    v, facade, signed_in = view
    facade.saved_session = True
    v.begin()
    assert wait_until(lambda: signed_in == [USER], timeout=3)
