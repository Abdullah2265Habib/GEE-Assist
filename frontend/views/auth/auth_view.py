"""Sign-in / sign-up screen: earth hero panel on the left, white card with the current step on the right."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from backend.auth_exceptions import AuthError
from backend.business.facade import IBusinessFacade
from backend.dto.user_dto import SignupResultDTO, UserDTO
from frontend import theme
from frontend.views.auth.google_page import GooglePage
from frontend.views.auth.hero_panel import HeroPanel, brand_row
from frontend.views.auth.login_page import LoginPage
from frontend.views.auth.signup_page import SignupPage
from frontend.views.auth.verification_page import DEFAULT_COOLDOWN_SECONDS, VerificationPage
from frontend.widgets.fade import fade_in
from frontend.widgets.form_widgets import FitStack, add_soft_shadow, link_button
from frontend.workers.task_worker import run_task

CARD_WIDTH = 580
SERVER_RETRY_MS = 10_000


class AuthView(QWidget):
    """Emits ``authenticated(UserDTO)`` once the user is signed in (password, Google or saved session)."""

    authenticated = pyqtSignal(object)

    def __init__(self, facade: IBusinessFacade, parent: QWidget | None = None):
        super().__init__(parent)
        self._facade = facade
        self._restoring = False
        self._pending_user: UserDTO | None = None
        self.setObjectName("AuthView")
        # Paint the background itself: otherwise the window behind shows through around the card,
        # e.g. under the logo at the top (white in the dark themes).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#AuthView {{ background: {theme.WHITE}; }}")

        # ---- pages
        self.login_page = LoginPage(facade)
        self.signup_page = SignupPage(facade)
        self.verification_page = VerificationPage(facade)
        self.google_page = GooglePage(facade)
        self.pages = FitStack()
        for page in (self.login_page, self.signup_page, self.verification_page, self.google_page):
            self.pages.addWidget(page)

        # ---- card
        self.card = QFrame(objectName="AuthCard")
        self.card.setFixedWidth(CARD_WIDTH)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(48, 40, 48, 36)
        card_layout.addWidget(self.pages)
        add_soft_shadow(self.card)

        # ---- server status under the card
        self.server_dot = QLabel("●")
        self.server_label = QLabel("Connecting to the GEE-Assist server…", objectName="Muted")
        self.server_retry = link_button("Retry")
        self.server_retry.hide()
        status = QHBoxLayout()
        status.setSpacing(6)
        status.addStretch(1)
        status.addWidget(self.server_dot)
        status.addWidget(self.server_label)
        status.addWidget(self.server_retry)
        status.addStretch(1)
        self._set_server_state(None)

        # ---- left side: the form (scrolls on small screens)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.card)
        row.addStretch(1)
        column.addLayout(row)
        column.addSpacing(18)
        column.addLayout(status)
        column.addStretch(1)
        inner = QWidget()
        inner.setLayout(column)
        inner.setContentsMargins(32, 32, 32, 32)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(inner)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(CARD_WIDTH + 2 * 32 + 12)
        scroll.setStyleSheet(f"QScrollArea, QScrollArea > QWidget > QWidget {{ background: {theme.WHITE}; }}")

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        brand = QWidget()
        brand.setLayout(brand_row())
        brand.layout().setContentsMargins(48, 36, 48, 0)
        left_layout.addWidget(brand)
        left_layout.addWidget(scroll, 1)

        # ---- right side: description + small animated Earth in the corner
        self.hero = HeroPanel()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(left, 3)
        layout.addWidget(self.hero, 2)

        # ---- wiring
        self.login_page.logged_in.connect(self._finish)
        self.login_page.create_account_requested.connect(self.show_signup)
        self.login_page.verification_required.connect(self._on_verification_required)
        self.login_page.google_requested.connect(self._start_google)
        self.signup_page.sign_in_requested.connect(lambda: self.show_login())
        self.signup_page.signed_up.connect(self._on_signed_up)
        self.verification_page.logged_in.connect(self._finish)
        self.verification_page.back_to_login.connect(self._back_from_verification)
        self.google_page.logged_in.connect(self._finish)
        self.google_page.cancelled.connect(self._back_from_google)
        self.server_retry.clicked.connect(self.check_server)

        self._server_timer = QTimer(self, interval=SERVER_RETRY_MS)
        self._server_timer.timeout.connect(self.check_server)

    # ------------------------------------------------------------------ start-up
    def begin(self) -> None:
        """Called at app start (while the intro plays): checks the server and restores a saved session."""
        self.check_server()
        self._restoring = True
        self.login_page.set_busy_message("Checking for a saved session…")
        run_task(self, self._facade.restore_session, on_success=self._on_restored, on_error=self._on_restore_failed)

    def _on_restored(self, user: UserDTO | None) -> None:
        self._restoring = False
        self.login_page.set_busy_message(None)
        if user is None:
            return
        if self.isVisible():
            self._finish(user)
        else:
            self._pending_user = user  # the intro is still playing: continue when it ends

    def _on_restore_failed(self, exc: Exception) -> None:
        self._restoring = False
        self.login_page.set_busy_message(None)
        if isinstance(exc, AuthError):
            self.login_page.banner.show_error(f"Could not restore your session. {exc}")

    def showEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        if self._pending_user is not None:
            user, self._pending_user = self._pending_user, None
            QTimer.singleShot(450, lambda: self._finish(user))  # let the fade-in be seen
        elif self.pages.currentWidget() is self.login_page and not self._restoring:
            self.login_page.focus_first_field()

    # ------------------------------------------------------------------ navigation
    def show_login(self, message: str = "", username: str = "", success: bool = False) -> None:
        self.login_page.reset()
        if username:
            self.login_page.prefill(username)
        if message:
            (self.login_page.banner.show_success if success else self.login_page.banner.show_error)(message)
        self._switch(self.login_page)
        self.login_page.focus_first_field()

    def show_signup(self) -> None:
        self.signup_page.reset()
        self._switch(self.signup_page)
        self.signup_page.focus_first_field()

    def reset(self, message: str = "") -> None:
        """Back to an empty sign-in form (e.g. after signing out)."""
        self.verification_page.stop()
        self.google_page.stop()
        self.login_page.reset(keep_username=True)
        self.show_login(message, success=bool(message))

    def _switch(self, page: QWidget) -> None:
        if self.pages.currentWidget() is page:
            return
        self.pages.setCurrentWidget(page)
        fade_in(page, 260)

    # ------------------------------------------------------------------ flows
    def _on_signed_up(self, result: SignupResultDTO, username: str, password: str) -> None:
        self.verification_page.start(
            result.verification_token,
            username,
            password,
            email=result.user.email,
            notice=None if result.email_sent else result.message,
            console_mode=result.email_delivery == "console",
            cooldown=DEFAULT_COOLDOWN_SECONDS if result.email_sent else 0,
        )
        self._switch(self.verification_page)

    def _on_verification_required(self, token: str, username: str, password: str) -> None:
        self.verification_page.start(
            token,
            username,
            password,
            remember=self.login_page.remember.isChecked(),
            notice="Your account isn't verified yet. Open the link in the email we sent you, "
            "or request a new one below.",
        )
        self._switch(self.verification_page)

    def _back_from_verification(self, message: str, username: str) -> None:
        self.show_login(message, username)

    def _start_google(self, remember: bool) -> None:
        self._switch(self.google_page)
        self.google_page.start(remember)

    def _back_from_google(self, message: str) -> None:
        self.show_login(message)

    def _finish(self, user: UserDTO) -> None:
        self.verification_page.stop()
        self.google_page.stop()
        self.authenticated.emit(user)

    # ------------------------------------------------------------------ server status
    def check_server(self) -> None:
        self.server_retry.hide()
        run_task(self, self._facade.is_server_available, on_success=self._set_server_state)

    def _set_server_state(self, online: bool | None) -> None:
        colour = {None: theme.SUBTLE, True: theme.LEAF, False: theme.ERROR}[online]
        self.server_dot.setStyleSheet(f"color: {colour}; font-size: 9pt;")
        if online is None:
            self.server_label.setText("Connecting to the GEE-Assist server…")
        elif online:
            self.server_label.setText("Connected to the GEE-Assist server")
            if hasattr(self, "_server_timer"):
                self._server_timer.stop()
        else:
            self.server_label.setText("Can't reach the GEE-Assist server.")
            self.server_retry.show()
            if hasattr(self, "_server_timer") and not self._server_timer.isActive():
                self._server_timer.start()  # keep retrying quietly
