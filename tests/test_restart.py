"""Restarting the app (after choosing a theme)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys  # noqa: E402

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication  # noqa: E402

from frontend import restart  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_restart_quits_then_starts_the_app_again(app, monkeypatch):
    events = []
    monkeypatch.setattr(QApplication, "quit", lambda *a: events.append("quit"))
    monkeypatch.setattr(restart.QProcess, "startDetached", lambda *args: events.append(args))

    restart.restart_app()
    assert events == ["quit"]  # nothing started until the app has closed

    app.aboutToQuit.emit()
    assert events[1] == (sys.executable, sys.argv, os.getcwd())
    app.aboutToQuit.disconnect(restart.start_again)
