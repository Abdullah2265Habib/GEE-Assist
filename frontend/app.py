from __future__ import annotations

import os
import sys

# Hide Qt Multimedia's FFmpeg chatter (version banner, stream info dump). Must be set before Qt loads.
os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg*=false")

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
from frontend.form_theme import apply_palette
from frontend.restart import start_again
from frontend.theme import apply_theme
from frontend.views.auth import AuthView
from frontend.views.home_window import HomeWindow
from frontend.views.startup_window import StartupWindow
from frontend.views.theme_choice_dialog import ask_theme_on_first_run
from frontend.widgets.wheel_guard import install_wheel_guard


def _use_own_taskbar_icon() -> None:
    """On Windows, give the app its own taskbar entry/icon instead of python.exe's."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GEEAssist.Desktop")


def _quiet_ffmpeg() -> None:
    """Silence FFmpeg's own stderr logging (e.g. the "[av1_mf] could not create MFT" lines printed
    while Qt probes for hardware encoders). Those messages are harmless; only fatal ones are kept."""
    import ctypes
    from pathlib import Path

    import PyQt6

    av_log_fatal = 8
    for dll in (Path(PyQt6.__file__).parent / "Qt6" / "bin").glob("avutil-*.dll"):
        try:
            ctypes.CDLL(str(dll)).av_log_set_level(av_log_fatal)
        except (OSError, AttributeError):
            pass
        return


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
    _quiet_ffmpeg()
    app = QApplication(sys.argv)
    app.setApplicationName("GEE-Assist")
    app.setWindowIcon(QIcon(str(APP_ICON)))
    apply_palette(app)  # the chosen theme, whatever colour scheme Windows uses
    apply_theme(app)
    install_wheel_guard(app)  # wheel only edits a field the user has selected
    # First start-up: ask for a theme. A dark one is applied by starting again in it.
    if "GEE_ASSIST_THEME" not in os.environ and ask_theme_on_first_run():
        start_again()
        return 0

    facade = build_business_facade()
    # Pause the active download cleanly so its files are closed and it resumes next time.
    app.aboutToQuit.connect(facade.shutdown_downloads)
    controller = AppController(facade)
    controller.start()
    return app.exec()
