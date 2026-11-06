"""Create a new account."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from backend.auth_exceptions import AuthError, ConflictError, FieldValidationError
from backend.business.facade import IBusinessFacade
from backend.business.user.signup_validation import clean_signup, password_strength, validate_signup
from backend.dto.user_dto import SignupDTO, SignupResultDTO
from frontend import theme
from frontend.views.auth.base_page import AuthPage, centered_row
from frontend.widgets.form_widgets import BusyButton, FormField, PasswordField, link_button
from frontend.workers.task_worker import run_task

_STRENGTH = {
    1: ("Weak", "#D9534F"),
    2: ("Fair", "#E3A13B"),
    3: ("Good", theme.OCEAN),
    4: ("Strong", theme.LEAF),
}


class SignupPage(AuthPage):
    signed_up = pyqtSignal(object, str, str)  # SignupResultDTO, username, password
    sign_in_requested = pyqtSignal()

    def __init__(self, facade: IBusinessFacade, parent: QWidget | None = None):
        super().__init__(facade, "Create your account", "Join GEE-Assist and start analysing satellite data in minutes.", parent)

        self.full_name = FormField("Full name", "e.g. Abdullah Habib")
        self.email = FormField("Email", "name@example.com", "We'll send a verification link here.")
        self.phone = FormField("Phone number", "+92 300 1234567", "Include your country code.")
        self.username = FormField("Username", "e.g. abdullah", "Letters, digits, '_' or '.'")
        self.password = PasswordField("Password", "At least 8 characters")
        self.confirm = PasswordField("Confirm password", "Repeat your password")

        self._fields = {
            "full_name": self.full_name,
            "email": self.email,
            "phone_number": self.phone,
            "username": self.username,
            "password": self.password,
            "confirm_password": self.confirm,
        }

        self.strength_bar = QProgressBar()
        self.strength_bar.setRange(0, 4)
        self.strength_bar.setTextVisible(False)
        self.strength_bar.setFixedHeight(4)
        self.strength_label = QLabel("", objectName="FieldHint")
        strength = QHBoxLayout()
        strength.setSpacing(10)
        strength.addWidget(self.strength_bar, 1)
        strength.addWidget(self.strength_label)
        self._strength_row = QWidget()
        self._strength_row.setLayout(strength)
        strength.setContentsMargins(0, 0, 0, 0)
        self._update_strength("")

        self.submit = BusyButton("Create account", "Creating account…")
        self.sign_in = link_button("Sign in")

        self.body.addWidget(self.full_name)
        self.body.addWidget(self.email)
        self.body.addLayout(self._pair(self.phone, self.username))
        self.body.addLayout(self._pair(self.password, self.confirm))
        self.body.addSpacing(-6)
        self.body.addWidget(self._strength_row)
        self.body.addSpacing(4)
        self.body.addWidget(self.submit)
        self.body.addSpacing(4)
        self.body.addLayout(centered_row(QLabel("Already have an account?", objectName="Muted"), self.sign_in))

        order = [f.input for f in self._fields.values()]
        for current, nxt in zip(order, order[1:]):
            current.returnPressed.connect(nxt.setFocus)
        self.confirm.input.returnPressed.connect(self._submit)
        self.password.input.textChanged.connect(self._update_strength)
        self.submit.clicked.connect(self._submit)
        self.sign_in.clicked.connect(self.sign_in_requested.emit)

    # ------------------------------------------------------------------ API
    def reset(self) -> None:
        super().reset()
        for field in self._fields.values():
            field.set_text("")
            field.clear_error()
        self.submit.set_busy(False)

    def focus_first_field(self) -> None:
        self.full_name.input.setFocus()

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _pair(left: QWidget, right: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        for widget in (left, right):
            column = QVBoxLayout()
            column.addWidget(widget)
            column.addStretch(1)
            row.addLayout(column, 1)
        return row

    def _form(self) -> SignupDTO:
        return SignupDTO(
            full_name=self.full_name.text(),
            email=self.email.text(),
            phone_number=self.phone.text(),
            username=self.username.text(),
            password=self.password.text(),
        )

    def _submit(self) -> None:
        if not self.submit.isEnabled():
            return
        self.banner.clear()
        for field in self._fields.values():
            field.clear_error()

        data = self._form()
        errors = validate_signup(data, self.confirm.text())
        if errors:
            self._show_field_errors(errors)
            return

        data = clean_signup(data)
        self._set_busy(True)
        run_task(
            self, self._facade.sign_up, data,
            on_success=lambda result: self._on_success(result, data),
            on_error=self._on_error,
        )

    def _on_success(self, result: SignupResultDTO, data: SignupDTO) -> None:
        self._set_busy(False)
        self.signed_up.emit(result, data.username, data.password)

    def _on_error(self, exc: Exception) -> None:
        self._set_busy(False)
        if isinstance(exc, FieldValidationError) and exc.field_errors:
            self._show_field_errors(exc.field_errors)
        elif isinstance(exc, ConflictError) and exc.field in self._fields:
            self._show_field_errors({exc.field: str(exc)})
        else:
            self.banner.show_error(str(exc) if isinstance(exc, AuthError) else "Something went wrong. Please try again.")

    def _show_field_errors(self, errors: dict[str, str]) -> None:
        first = None
        for name, message in errors.items():
            field = self._fields.get(name)
            if field is None:
                self.banner.show_error(message)
                continue
            field.set_error(message)
            first = first or field
        if first is not None:
            first.input.setFocus()
            first.input.selectAll()

    def _update_strength(self, password: str) -> None:
        score = password_strength(password)
        self._strength_row.setVisible(score > 0)
        if not score:
            return
        label, colour = _STRENGTH[score]
        self.strength_bar.setValue(score)
        self.strength_bar.setStyleSheet(
            f"QProgressBar {{ background: {theme.MINT}; border: none; border-radius: 2px; }}"
            f"QProgressBar::chunk {{ background: {colour}; border-radius: 2px; }}"
        )
        self.strength_label.setText(f"Password strength: {label}")

    def _set_busy(self, busy: bool) -> None:
        self.submit.set_busy(busy)
        for field in self._fields.values():
            field.input.setEnabled(not busy)
        self.sign_in.setEnabled(not busy)
