"""The light and dark palettes, and which one the app starts with."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from frontend import palette

DARK = [palette.DARK_GREEN, palette.DARK_GREY]


def _luminance(hex_value: str) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_value[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_every_palette_names_the_same_colours():
    for colours in DARK:
        assert colours.keys() == palette.LIGHT.keys()


@pytest.mark.parametrize("colours", DARK, ids=["dark-green", "dark-grey"])
def test_dark_text_and_buttons_are_light_and_readable(colours):
    for surface in ("WHITE", "PAGE_BG", "FIELD_BG"):
        for text in ("INK", "TEXT", "MUTED", "LEAF", "OCEAN", "ERROR", "SUCCESS"):
            assert contrast(colours[text], colours[surface]) >= 4.5, (text, surface)
        assert _luminance(colours["INK"]) > _luminance(colours[surface])  # light text on a dark surface
    for accent in ("LEAF", "OCEAN", "LEAF_DARK", "OCEAN_DARK"):  # the green-to-blue buttons
        assert contrast(colours["PRIMARY_TEXT"], colours[accent]) >= 4.5, accent


def test_tests_run_in_the_light_theme():
    assert palette.THEME == "light" and palette.ACTIVE is palette.LIGHT and not palette.IS_DARK


@pytest.mark.parametrize("name", ["dark-green", "dark-grey"])
def test_the_app_starts_in_the_chosen_theme(name):
    env = dict(os.environ, GEE_ASSIST_THEME=name, QT_QPA_PLATFORM="offscreen")
    code = "from frontend import palette, theme; print(palette.IS_DARK, theme.WHITE == palette.PALETTES[%r]['WHITE'])"
    out = subprocess.run([sys.executable, "-c", code % name], env=env, capture_output=True, text=True,
                         cwd=Path(__file__).resolve().parents[1], check=True).stdout.split()
    assert out == ["True", "True"]
