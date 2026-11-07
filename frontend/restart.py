"""Restart GEE-Assist (used after choosing a theme, which is applied at start-up)."""

from __future__ import annotations

import os
import sys

from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import QApplication


def restart_app() -> None:
    """Close this window of the app and start a new one.

    The new one starts once this one has finished closing (the active download is
    paused first, see ``app.py``), so the two never work on a download at once.
    """
    app = QApplication.instance()
    app.aboutToQuit.connect(start_again)  # after the download shutdown, connected earlier
    app.quit()


def start_again() -> None:
    """Start a new copy of the app (this one should then close)."""
    args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv  # a packaged .exe is sys.executable
    QProcess.startDetached(sys.executable, args, os.getcwd())
