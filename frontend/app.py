from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

try:  # Qt requires QtWebEngine to be imported before QApplication is created (AOI map)
    import PyQt6.QtWebEngineWidgets  # noqa: F401
except ImportError:
    pass

from backend.bootstrap import build_business_facade
from frontend.form_theme import apply_light_mode
from frontend.views.main_window import MainWindow
from frontend.widgets.wheel_guard import install_wheel_guard


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("GEE-Assist")
    apply_light_mode(app)
    install_wheel_guard(app)  # wheel only edits a field the user has selected

    window = MainWindow(build_business_facade())
    window.show()
    return app.exec()
