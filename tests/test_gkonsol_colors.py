"""The terminal's colours follow the theme and stay readable."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication  # noqa: E402

from frontend import palette  # noqa: E402
from frontend.gkonsol import colors, text  # noqa: E402
from tests.test_palette import contrast  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_every_style_has_a_colour():
    assert set(colors.STYLE_COLOURS) == set(text.STYLES)


@pytest.mark.parametrize("theme", ["light", "dark-green", "dark-grey"])
def test_warnings_are_readable_on_each_terminal_background(theme):
    colours = palette.PALETTES[theme]
    background = colours["FIELD_BG"] if theme != "light" else colours["WHITE"]
    assert contrast(colors.WARNING[theme], background) >= 4.5


def test_text_formats_carry_the_colour_and_weight(app):
    formats = colors.char_formats()
    assert formats[text.ERROR].foreground().color().name().upper() == palette.ACTIVE["ERROR"].upper()
    assert formats[text.COMMAND].fontWeight() > formats[text.TEXT].fontWeight()


def test_the_font_is_fixed_width(app):
    font = colors.monospace_font()
    assert font.fixedPitch() and font.pointSize() == colors.FONT_POINT_SIZE
