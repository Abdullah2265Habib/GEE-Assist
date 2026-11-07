"""The project's asset files."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from frontend import appearance, assets


def test_every_theme_has_its_own_project_icon():
    assert assets.APP_ICONS.keys() == appearance.THEMES.keys()
    assert len(set(assets.APP_ICONS.values())) == len(assets.APP_ICONS)
    assert all(path.is_file() for path in assets.APP_ICONS.values())


def test_tests_use_the_light_icon():
    assert assets.APP_ICON.name == "light_icon.png"


@pytest.mark.parametrize("name, icon", [("dark-green", "dark_blue_green_icon.png"), ("dark-grey", "dark_grey_icon.png")])
def test_the_icon_follows_the_theme(name, icon):
    env = dict(os.environ, GEE_ASSIST_THEME=name)
    out = subprocess.run([sys.executable, "-c", "from frontend import assets; print(assets.APP_ICON.name)"],
                         env=env, capture_output=True, text=True, check=True,
                         cwd=Path(__file__).resolve().parents[1]).stdout.strip()
    assert out == icon
