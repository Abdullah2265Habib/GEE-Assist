"""'Check your email' page: waits for the user to open the verification link, then signs them in."""

from __future__ import annotations

from html import escape

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QWidget

from backend.auth_exceptions import (
    AuthError,
    ConflictError,
    FieldValidationError,
    RateLimitedError,
    ServerUnavailableError,
    SessionExpiredError,
)
from backend.business.facade import IBusinessFacade
from backend.business.user.signup_validation import EMAIL_PATTERN
from backend.dto.user_dto import UserDTO, VerificationStatusDTO
from frontend.views.auth.base_page import AuthPage, centered_row
from frontend.widgets.form_widgets import BusyButton, FormField, link_button
from frontend.widgets.icons import envelope_pixmap
from frontend.workers.task_worker import run_task

POLL_INTERVAL_MS = 4000
DEFAULT_COOLDOWN_SECONDS = 60


class VerificationPage(AuthPage):
    logged_in = pyqtSignal(object)        # UserDTO
    back_to_login = pyqtSignal(str, str)  # message for the login page, username to prefill

    def __init__(self, facade: IBusinessFacade, parent: QWidget | None = None):
        super().__init__(facade, "Verify your email", "", parent)
        self._token = ""
        self._username = ""
        self._password = ""
        self._remember = False
        self._email: str | None = None
        self._active = False
        self._checking = False
        self._cooldown = 0

        icon = QLabel()
        icon.setPixmap(envelope_pixmap(76))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body.insertWidget(0, icon)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setTextFormat(Qt.TextFormat.RichText)

        self.waiting = QProgressBar(objectName="BusyBar")
        self.waiting.setRange(0, 0)  # indeterminate
        self.waiting.setTextVisible(False)
        self.waiting_label = QLabel("Waiting for you to open the link…", objectName="Muted")
        self.waiting_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.check_now = BusyButton("I've verified my email", "Checking…")
        self.resend = BusyButton("Resend email", "Sending…", object_name="SecondaryButton")

        self.change_email_link = link_button("Wrong email? Change it")
        self.new_email = FormField("New email address", "name@example.com")
        self.update_email = BusyButton("Update and resend", "Sending…", object_name="SecondaryButton")
        self._change_box = QWidget()
        change_layout = QHBoxLayout(self._change_box)
        change_layout.setContentsMargins(0, 0, 0, 0)
        change_layout.setSpacing(10)
        change_layout.addWidget(self.new_email, 1)
        change_layout.addWidget(self.update_email, 0, Qt.AlignmentFlag.AlignBottom)
        self._change_box.hide()

        self.back = link_button("Back to sign in")

        self.body.addWidget(self.waiting)
        self.body.addWidget(self.waiting_label)
        self.body.addSpacing(4)
        self.body.addWidget(self.check_now)
        self.body.addWidget(self.resend)
        self.body.addLayout(centered_row(self.change_email_link))
        self.body.addWidget(self._change_box)
        self.body.addLayout(centered_row(self.back))

        self._poll_timer = QTimer(self, interval=POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(lambda: self._check_status(manual=False))
        self._cooldown_timer = QTimer(self, interval=1000)
        self._cooldown_timer.timeout.connect(self._tick_cooldown)

        self.check_now.clicked.connect(lambda: self._check_status(manual=True))
        self.resend.clicked.connect(lambda: self._resend(None))
        self.change_email_link.clicked.connect(self._toggle_change_email)
        self.update_email.clicked.connect(self._submit_new_email)
        self.new_email.input.returnPressed.connect(self._submit_new_email)
        self.back.clicked.connect(lambda: self._leave("", self._username))

    # ------------------------------------------------------------------ API
    def start(
        self,
        verification_token: str,
        username: str,
        password: str,
        *,
        remember: bool = False,
        email: str | None = None,
        notice: str | None = None,
        console_mode: bool = False,
        cooldown: int = 0,
    ) -> None:
        self.reset()
        self._token, self._username, self._password, self._remember = verification_token, username, password, remember
        self._active = True
        self._set_email(email)
        self._change_box.hide()
        self.new_email.set_text("")
        self.new_email.clear_error()

        if console_mode:
            self.banner.show_info(
                "Development server: the verification link was printed in the server terminal "
                "instead of being emailed. Open it in your browser."
            )
        elif notice:
            self.banner.show_info(notice)

        self._start_cooldown(cooldown)
        self._poll_timer.start()
        self._check_status(manual=False)

    def stop(self) -> None:
        self._active = False
        self._poll_timer.stop()
        self._cooldown_timer.stop()

    # ------------------------------------------------------------------ status
    def _check_status(self, manual: bool) -> None:
        if not self._active or self._checking:
            return
        self._checking = True
        if manual:
            self.check_now.set_busy(True)
        run_task(
            self, self._facade.get_verification_status, self._token,
            on_success=lambda status: self._on_status(status, manual),
            on_error=lambda exc: self._on_status_error(exc, manual),
        )

    def _on_status(self, status: VerificationStatusDTO, manual: bool) -> None:
        self._checking = False
        self.check_now.set_busy(False)
        if not self._active:
            return
        self._set_email(status.email)
        if status.is_verified:
            self._sign_in()
        elif manual:
            self.banner.show_error("Your email isn't verified yet. Open the link we sent you, then try again.")

    def _on_status_error(self, exc: Exception, manual: bool) -> None:
        self._checking = False
        self.check_now.set_busy(False)
        if not self._active:
            return
        if isinstance(exc, SessionExpiredError):
            self._leave("Your verification session has expired. Sign in again to continue.", self._username)
        elif manual or not isinstance(exc, ServerUnavailableError):
            self.banner.show_error(str(exc))
        # background polls ignore brief network hiccups and simply try again

    def _sign_in(self) -> None:
        self.stop()
        self.waiting_label.setText("Email verified! Signing you in…")
        self.banner.show_success("Your email address is verified.")
        for button in (self.check_now, self.resend, self.change_email_link, self.back):
            button.setEnabled(False)
        run_task(
            self, self._facade.log_in, self._username, self._password, self._remember,
            on_success=self._on_logged_in,
            on_error=lambda exc: self._leave(f"Your email is verified. {exc} Please sign in.", self._username),
        )

    def _on_logged_in(self, user: UserDTO) -> None:
        self._password = ""
        self.logged_in.emit(user)

    # ------------------------------------------------------------------ resend / change email
    def _toggle_change_email(self) -> None:
        visible = not self._change_box.isVisible()
        self._change_box.setVisible(visible)
        if visible:
            self.new_email.set_text(self._email or "")
            self.new_email.input.setFocus()
            self.new_email.input.selectAll()

    def _submit_new_email(self) -> None:
        email = self.new_email.text().strip()
        if not EMAIL_PATTERN.fullmatch(email):
            self.new_email.set_error("Enter a valid email address")
            return
        self._resend(email)

    def _resend(self, new_email: str | None) -> None:
        if self._cooldown > 0:
            return
        self.banner.clear()
        button = self.update_email if new_email else self.resend
        button.set_busy(True)
        run_task(
            self, self._facade.resend_verification_email, self._token, new_email,
            on_success=lambda message: self._on_resent(message, button),
            on_error=lambda exc: self._on_resend_error(exc, button, new_email),
        )

    def _on_resent(self, message: str, button: BusyButton) -> None:
        button.set_busy(False)
        self.banner.show_success(message)
        self._change_box.hide()
        self._start_cooldown(DEFAULT_COOLDOWN_SECONDS)
        self._check_status(manual=False)  # picks up the new email address

    def _on_resend_error(self, exc: Exception, button: BusyButton, new_email: str | None) -> None:
        button.set_busy(False)
        if isinstance(exc, RateLimitedError):
            self._start_cooldown(exc.retry_after)
            self.banner.show_error(str(exc))
        elif isinstance(exc, ConflictError) and "verified" in str(exc).lower():
            self._check_status(manual=False)  # already verified: sign in
        elif isinstance(exc, SessionExpiredError):
            self._leave("Your verification session has expired. Sign in again to continue.", self._username)
        elif new_email and isinstance(exc, (ConflictError, FieldValidationError)):
            self.new_email.set_error(str(exc))
        else:
            self.banner.show_error(str(exc) if isinstance(exc, AuthError) else "Could not send the email.")

    def _start_cooldown(self, seconds: int) -> None:
        self._cooldown = max(0, int(seconds))
        self._tick_cooldown(initial=True)
        if self._cooldown > 0:
            self._cooldown_timer.start()

    def _tick_cooldown(self, initial: bool = False) -> None:
        if not initial:
            self._cooldown = max(0, self._cooldown - 1)
        waiting = self._cooldown > 0
        self.resend.setEnabled(not waiting)
        self.update_email.setEnabled(not waiting)
        self.resend.setText(f"Resend email in {self._cooldown}s" if waiting else "Resend email")
        if not waiting:
            self._cooldown_timer.stop()

    # ------------------------------------------------------------------ helpers
    def _set_email(self, email: str | None) -> None:
        if email:
            self._email = email
        target = f"<b>{escape(self._email)}</b>" if self._email else "your email address"
        self.subtitle.setText(f"We sent a verification link to {target}.<br>Open it to activate your account.")

    def _leave(self, message: str, username: str) -> None:
        self.stop()
        self._password = ""
        self.back_to_login.emit(message, username)

    def reset(self) -> None:
        super().reset()
        self.waiting_label.setText("Waiting for you to open the link…")
        for button in (self.check_now, self.resend, self.change_email_link, self.back):
            button.setEnabled(True)
        self.check_now.set_busy(False)
        self.resend.set_busy(False)
        self.update_email.set_busy(False)
