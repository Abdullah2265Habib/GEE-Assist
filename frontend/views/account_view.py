"""Signed-in user's account card (data from /auth/me)."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from backend.auth_exceptions import AuthError, SessionExpiredError
from backend.business.facade import IBusinessFacade
from backend.dto.user_dto import UserDTO
from frontend import theme
from frontend.widgets.form_widgets import Banner, BusyButton, add_soft_shadow
from frontend.workers.task_worker import run_task

_PROVIDERS = {"local": "Username and password", "google": "Google"}


def _format_date(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.astimezone().strftime("%d %b %Y, %H:%M")


class Avatar(QLabel):
    def __init__(self, size: int = 64, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"border-radius: {size // 2}px; color: {theme.WHITE}; font-family: '{theme.SERIF}';"
            f"font-size: {max(9, size // 4)}pt;"
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {theme.LEAF}, stop:1 {theme.OCEAN});"
        )

    def set_user(self, user: UserDTO) -> None:
        self.setText(user.initials)


class AccountView(QFrame):
    session_expired = pyqtSignal()

    def __init__(self, facade: IBusinessFacade, parent: QWidget | None = None):
        super().__init__(parent)
        self._facade = facade
        self.setObjectName("AuthCard")
        self.setFixedWidth(560)
        add_soft_shadow(self)

        self.avatar = Avatar(72)
        self.greeting = QLabel(objectName="Title")
        self.summary = QLabel(objectName="Subtitle")
        self.summary.setWordWrap(True)
        head_text = QVBoxLayout()
        head_text.setSpacing(4)
        head_text.addWidget(self.greeting)
        head_text.addWidget(self.summary)
        head = QHBoxLayout()
        head.setSpacing(18)
        head.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)
        head.addLayout(head_text, 1)

        self.banner = Banner()
        self._values: dict[str, QLabel] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(12)
        rows = [("username", "Username"), ("email", "Email"), ("phone", "Phone"), ("role", "Role"),
                ("provider", "Sign-in method"), ("created", "Member since"), ("last_login", "Last sign-in")]
        for row, (key, title) in enumerate(rows):
            label = QLabel(title, objectName="Muted")
            value = QLabel()
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setStyleSheet(f"color: {theme.INK};")
            grid.addWidget(label, row, 0)
            grid.addWidget(value, row, 1)
            self._values[key] = value
        grid.setColumnStretch(1, 1)

        self.refresh = BusyButton("Refresh details", "Refreshing…", object_name="SecondaryButton")
        self.refresh.clicked.connect(self.reload)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 36, 40, 34)
        layout.setSpacing(18)
        layout.addLayout(head)
        layout.addWidget(self.banner)
        separator = QFrame()
        separator.setFixedHeight(1)
        separator.setStyleSheet(f"background: {theme.BORDER};")
        layout.addWidget(separator)
        layout.addLayout(grid)
        layout.addWidget(self.refresh)

    def set_user(self, user: UserDTO) -> None:
        first_name = user.full_name.split()[0] if user.full_name.split() else user.username
        self.avatar.set_user(user)
        self.greeting.setText(f"Welcome, {first_name}!")
        self.summary.setText("You're signed in to GEE-Assist. Your analysis workspace will open from here.")
        verified = "  ✓ verified" if user.email_verified else "  (not verified)"
        self._values["username"].setText(user.username)
        self._values["email"].setText((user.email or "—") + (verified if user.email else ""))
        self._values["phone"].setText(user.phone_number or "—")
        self._values["role"].setText("Administrator" if user.is_admin else "User")
        self._values["provider"].setText(_PROVIDERS.get(user.auth_provider, user.auth_provider.title()))
        self._values["created"].setText(_format_date(user.created_at))
        self._values["last_login"].setText(_format_date(user.last_login_at))

    def reload(self) -> None:
        self.banner.clear()
        self.refresh.set_busy(True)
        run_task(self, self._facade.reload_current_user, on_success=self._on_reloaded, on_error=self._on_error)

    def _on_reloaded(self, user: UserDTO) -> None:
        self.refresh.set_busy(False)
        self.set_user(user)

    def _on_error(self, exc: Exception) -> None:
        self.refresh.set_busy(False)
        if isinstance(exc, SessionExpiredError):
            self.session_expired.emit()
        else:
            self.banner.show_error(str(exc) if isinstance(exc, AuthError) else "Could not load your details.")
