from __future__ import annotations

import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QLabel

from frontend.assets import APP_ICON
from frontend.views.startup_window import StartupWindow


def _use_own_taskbar_icon() -> None:
    """On Windows, give the app its own taskbar entry/icon instead of python.exe's."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GEEAssist.Desktop")


def run() -> int:
    _use_own_taskbar_icon()
    app = QApplication(sys.argv)
    app.setApplicationName("GEE-Assist")
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(str(APP_ICON)))

    placeholder = QLabel("GEE-Assist")  # replaced by the sign-in view
    window = StartupWindow(placeholder)
    window.start()
    return app.exec()
