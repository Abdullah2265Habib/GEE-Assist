"""The sign-in screen in the dark themes: no white left from the light theme."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

# Draws the sign-in screen in a dark theme and prints the colour behind the logo at the top.
SCRIPT = """
import os, sys
from unittest.mock import MagicMock
import PyQt6.QtWebEngineWidgets  # before QApplication, as in app.py (the sign-in picture uses it)
from PyQt6.QtWidgets import QApplication
app = QApplication([])
from frontend import theme
from frontend.views.auth import AuthView
from frontend.views.startup_window import StartupWindow
window = StartupWindow(AuthView(MagicMock()), play_intro=False)  # hosted as in the app
window.resize(1366, 700)
window.show()
app.processEvents()
image = window.grab().toImage()
print(image.pixelColor(400, 12).name(), theme.WHITE.lower())
sys.stdout.flush()
os._exit(0)  # skip Qt's teardown: the result is printed
"""


@pytest.mark.parametrize("name", ["dark-green", "dark-grey"])
def test_top_of_the_sign_in_screen_follows_the_dark_theme(name):
    env = dict(os.environ, GEE_ASSIST_THEME=name, QT_QPA_PLATFORM="offscreen")
    out = subprocess.run([sys.executable, "-c", SCRIPT], env=env, capture_output=True, text=True, check=True,
                         cwd=Path(__file__).resolve().parents[1]).stdout.split()
    top, surface = out[-2], out[-1]
    assert top == surface != "#ffffff"
