from __future__ import annotations

import sys

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

try:  # Qt requires QtWebEngine to be imported before QApplication is created (animated SVG, AOI map)
    import PyQt6.QtWebEngineWidgets  # noqa: F401
except ImportError:
    pass

from backend.bootstrap import build_business_facade
from backend.business.facade import IBusinessFacade
from backend.dto.user_dto import UserDTO
from frontend.assets import APP_ICON
from frontend.theme import apply_theme
from frontend.views.auth import AuthView
from frontend.views.home_window import HomeWindow
from frontend.views.startup_window import StartupWindow


def _use_own_taskbar_icon() -> None:
    """On Windows, give the app its own taskbar entry/icon instead of python.exe's."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GEEAssist.Desktop")


class AppController(QObject):
    """Intro video -> sign in -> home window; signing out returns to the sign-in screen."""

    def __init__(self, facade: IBusinessFacade):
        super().__init__()
        self._facade = facade
        self.auth_view = AuthView(facade)
        self.startup = StartupWindow(self.auth_view)
        self.home: HomeWindow | None = None
        self.auth_view.authenticated.connect(self._on_authenticated)

    def start(self) -> None:
        self.auth_view.begin()  # server check + saved-session restore run while the intro plays
        self.startup.start()

    def _on_authenticated(self, user: UserDTO) -> None:
        self.home = HomeWindow(self._facade, user)
        self.home.signed_out.connect(self._on_signed_out)
        self.home.showMaximized()
        self.startup.hide()

    def _on_signed_out(self, message: str) -> None:
        self._facade.log_out()
        self.auth_view.reset(message)
        self.startup.showMaximized()
        if self.home is not None:
            self.home.close()
            self.home.deleteLater()
            self.home = None


def run() -> int:
    _use_own_taskbar_icon()
    app = QApplication(sys.argv)
    app.setApplicationName("GEE-Assist")
    app.setWindowIcon(QIcon(str(APP_ICON)))
    apply_theme(app)

    controller = AppController(build_business_facade())
    controller.start()
    return app.exec()
