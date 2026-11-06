"""Sign in with username + password, or start Google sign-in."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QWidget

from backend.auth_exceptions import AuthError, InvalidCredentialsError, VerificationRequiredError
from backend.business.facade import IBusinessFacade
from backend.dto.user_dto import UserDTO
from frontend.views.auth.base_page import AuthPage, centered_row
from frontend.widgets.form_widgets import BusyButton, FormField, PasswordField, h_line, link_button
from frontend.widgets.icons import google_icon
from frontend.workers.task_worker import run_task


class LoginPage(AuthPage):
    logged_in = pyqtSignal(object)                    # UserDTO
    verification_required = pyqtSignal(str, str, str)  # verification_token, username, password
    create_account_requested = pyqtSignal()
    google_requested = pyqtSignal(bool)               # remember

    def __init__(self, facade: IBusinessFacade, parent: QWidget | None = None):
        super().__init__(facade, "Welcome back", "Sign in to continue exploring Earth with GEE-Assist.", parent)

        self.username = FormField("Username", "Your username")
        self.password = PasswordField("Password", "Your password")
        self.remember = QCheckBox("Keep me signed in")
        self.remember.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remember.setChecked(True)  # reopening the app skips sign-in until the session runs out
        self.remember.setToolTip(
            "Stay signed in on this computer for a limited time (SESSION_DURATION in .env). "
            "The session is kept in Windows Credential Manager."
        )

        self.submit = BusyButton("Sign in", "Signing in…")
        self.google = QPushButton("  Continue with Google", objectName="SecondaryButton")
        self.google.setIcon(google_icon())
        self.google.setIconSize(QSize(18, 18))
        self.google.setMinimumHeight(44)
        self.google.setCursor(Qt.CursorShape.PointingHandCursor)

        divider = QHBoxLayout()
        divider.setSpacing(12)
        divider.addWidget(h_line(), 1)
        divider.addWidget(QLabel("or", objectName="Divider"))
        divider.addWidget(h_line(), 1)

        self.create_account = link_button("Create an account")

        self.body.addWidget(self.username)
        self.body.addWidget(self.password)
        self.body.addWidget(self.remember)
        self.body.addSpacing(4)
        self.body.addWidget(self.submit)
        self.body.addLayout(divider)
        self.body.addWidget(self.google)
        self.body.addSpacing(6)
        self.body.addLayout(centered_row(QLabel("New to GEE-Assist?", objectName="Muted"), self.create_account))

        self.submit.clicked.connect(self._submit)
        self.username.input.returnPressed.connect(self.password.input.setFocus)
        self.password.input.returnPressed.connect(self._submit)
        self.google.clicked.connect(lambda: self.google_requested.emit(self.remember.isChecked()))
        self.create_account.clicked.connect(self.create_account_requested.emit)

    # ------------------------------------------------------------------ API
    def reset(self, keep_username: bool = True) -> None:
        super().reset()
        if not keep_username:
            self.username.set_text("")
        self.password.set_text("")
        self.username.clear_error()
        self.password.clear_error()
        self._set_busy(False)

    def prefill(self, username: str) -> None:
        self.username.set_text(username)
        self.password.input.setFocus()

    def focus_first_field(self) -> None:
        (self.password.input if self.username.text() else self.username.input).setFocus()

    def set_busy_message(self, message: str | None) -> None:
        """Used while the saved session is being restored at start-up."""
        self._set_busy(bool(message))
        if message:
            self.banner.show_info(message)
        else:
            self.banner.clear()

    # ------------------------------------------------------------------ internals
    def _submit(self) -> None:
        if not self.submit.isEnabled():
            return
        self.banner.clear()
        username, password = self.username.text().strip(), self.password.text()
        ok = True
        if not username:
            self.username.set_error("Enter your username")
            ok = False
        if not password:
            self.password.set_error("Enter your password")
            ok = False
        if not ok:
            return

        self._set_busy(True)
        run_task(
            self, self._facade.log_in, username, password, self.remember.isChecked(),
            on_success=self._on_success,
            on_error=lambda exc: self._on_error(exc, username, password),
        )

    def _on_success(self, user: UserDTO) -> None:
        self._set_busy(False)
        self.password.set_text("")
        self.logged_in.emit(user)

    def _on_error(self, exc: Exception, username: str, password: str) -> None:
        self._set_busy(False)
        if isinstance(exc, VerificationRequiredError):
            self.verification_required.emit(exc.verification_token, username, password)
            return
        self.banner.show_error(str(exc) if isinstance(exc, AuthError) else "Something went wrong. Please try again.")
        if isinstance(exc, InvalidCredentialsError):
            self.password.input.selectAll()
            self.password.input.setFocus()

    def _set_busy(self, busy: bool) -> None:
        self.submit.set_busy(busy)
        for widget in (self.username.input, self.password.input, self.remember, self.google, self.create_account):
            widget.setEnabled(not busy)
