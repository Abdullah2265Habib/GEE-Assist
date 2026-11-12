"""Filtering Qt's known-harmless warnings."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from frontend.qt_messages import is_harmless  # noqa: E402


def test_only_the_video_players_shutdown_warnings_are_harmless():
    assert is_harmless("QObject::disconnect: wildcard call disconnects from destroyed signal of "
                       "QFFmpeg::VideoRenderer::unnamed")
    assert not is_harmless("QObject::disconnect: wildcard call disconnects from destroyed signal of MyWidget")
    assert not is_harmless("QPainter::begin: Paint device returned engine == 0")


# Prints one harmless and one real warning through Qt with the filter installed.
SCRIPT = """
from PyQt6.QtCore import qWarning
from frontend.qt_messages import install_message_filter
install_message_filter()
qWarning(b"QObject::disconnect: wildcard call disconnects from destroyed signal of QFFmpeg::Demuxer::unnamed")
qWarning(b"a real warning")
"""


def test_harmless_warnings_are_hidden_and_others_still_shown():
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True, check=True, env=env,
                            cwd=Path(__file__).resolve().parents[1])
    assert "QFFmpeg" not in result.stderr
    assert "a real warning" in result.stderr
