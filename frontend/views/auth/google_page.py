"""Google sign-in: open the browser, then poll the server until the user has finished there."""

from __future__ import annotations

from PyQt6.QtCore import QElapsedTimer, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QLabel, QProgressBar, QWidget

from backend.auth_exceptions import AuthError, NotFoundError, ServerUnavailableError
from backend.business.facade import IBusinessFacade
from backend.dto.user_dto import GoogleSignInDTO, UserDTO
from frontend.views.auth.base_page import AuthPage, centered_row
from frontend.widgets.form_widgets import BusyButton, link_button
from frontend.workers.task_worker import run_task


class GooglePage(AuthPage):
    logged_in = pyqtSignal(object)   # UserDTO
    cancelled = pyqtSignal(str)      # message for the login page ("" = user cancelled)

    def __init__(self, facade: IBusinessFacade, parent: QWidget | None = None):
        super().__init__(
            facade,
            "Continue with Google",
            "Finish signing in with Google in your web browser. GEE-Assist continues automatically.",
            parent,
        )
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._session: GoogleSignInDTO | None = None
        self._remember = False
        self._polling = False
        self._active = False
        self._elapsed = QElapsedTimer()

        self.waiting = QProgressBar(objectName="BusyBar")
        self.waiting.setRange(0, 0)
        self.waiting.setTextVisible(False)
        self.status = QLabel("Opening Google sign-in…", objectName="Muted")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setWordWrap(True)

        self.reopen = BusyButton("Open the browser again", "Opening…", object_name="SecondaryButton")
        self.cancel = link_button("Cancel and go back")

        self.body.addWidget(self.waiting)
        self.body.addWidget(self.status)
        self.body.addSpacing(6)
        self.body.addWidget(self.reopen)
        self.body.addLayout(centered_row(self.cancel))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self.reopen.clicked.connect(self._open_browser)
        self.cancel.clicked.connect(lambda: self._finish(""))

    # ------------------------------------------------------------------ API
    def start(self, remember: bool) -> None:
        self.reset()
        self._remember = remember
        self._active = True
        self._session = None
        self.status.setText("Opening Google sign-in…")
        self.reopen.set_busy(True)
        run_task(self, self._facade.start_google_sign_in, on_success=self._on_started, on_error=self._on_failed)

    def stop(self) -> None:
        self._active = False
        self._timer.stop()

    # ------------------------------------------------------------------ internals
    def _on_started(self, session: GoogleSignInDTO) -> None:
        if not self._active:
            return
        self._session = session
        self.reopen.set_busy(False)
        self._open_browser()
        self._elapsed.start()
        self._timer.start(session.poll_interval * 1000)

    def _open_browser(self) -> None:
        if self._session is None:
            return
        if QDesktopServices.openUrl(QUrl(self._session.authorization_url)):
            self.status.setText("Waiting for you to finish signing in with Google in your browser…")
        else:
            self.status.setText("Could not open your browser. Copy this link into it:")
            self.banner.show_info(self._session.authorization_url)

    def _poll(self) -> None:
        if not self._active or self._session is None or self._polling:
            return
        if self._elapsed.elapsed() > self._session.expires_in * 1000:
            self._finish("Google sign-in took too long and expired. Please try again.")
            return
        self._polling = True
        run_task(
            self, self._facade.poll_google_sign_in, self._session.session_id, self._remember,
            on_success=self._on_polled,
            on_error=self._on_poll_error,
        )

    def _on_polled(self, user: UserDTO | None) -> None:
        self._polling = False
        if not self._active or user is None:
            return  # still waiting
        self.stop()
        self.status.setText("Signed in with Google!")
        self.logged_in.emit(user)

    def _on_poll_error(self, exc: Exception) -> None:
        self._polling = False
        if not self._active:
            return
        if isinstance(exc, ServerUnavailableError):
            self.status.setText("Lost connection to the server, retrying…")
            return
        if isinstance(exc, NotFoundError):
            self._finish("Google sign-in expired. Please try again.")
            return
        self._finish(str(exc) if isinstance(exc, AuthError) else "Google sign-in failed. Please try again.")

    def _on_failed(self, exc: Exception) -> None:
        self.reopen.set_busy(False)
        if self._active:
            self._finish(str(exc) if isinstance(exc, AuthError) else "Could not start Google sign-in.")

    def _finish(self, message: str) -> None:
        self.stop()
        self.cancelled.emit(message)
