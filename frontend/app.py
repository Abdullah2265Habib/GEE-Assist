from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

try:  # Qt requires QtWebEngine to be imported before QApplication is created (AOI map)
    import PyQt6.QtWebEngineWidgets  # noqa: F401
except ImportError:
    pass

from backend.bootstrap import build_business_facade
from frontend.views.main_window import MainWindow


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("GEE-Assist")
    app.setStyle("Fusion")

    window = MainWindow(build_business_facade())
    window.show()
    return app.exec()
