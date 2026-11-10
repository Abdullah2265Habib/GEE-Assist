"""The terminal's colours and font, from the app's theme.

Every text style (``text.TEXT``, ``text.ERROR``...) gets a colour of the active palette,
so the terminal follows the light and dark themes like the rest of the app. In the
dark themes the output area uses the darker field colour, as a terminal usually does.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QFontDatabase, QTextCharFormat

from frontend import palette
from frontend.gkonsol import text

# Amber for warnings: readable on each theme's terminal background.
WARNING = {"light": "#9A6700", "dark-green": "#F2C46D", "dark-grey": "#F0C674"}
FONT_FAMILIES = ("Cascadia Mono", "Cascadia Code", "Consolas", "Courier New")
FONT_POINT_SIZE = 10


def _colour(name: str) -> str:
    return palette.ACTIVE[name]


BACKGROUND = _colour("FIELD_BG") if palette.IS_DARK else _colour("WHITE")
HEADER = _colour("WHITE") if palette.IS_DARK else _colour("FOAM")
BORDER = _colour("BORDER")
SELECTION = _colour("OCEAN")

# style -> (colour, bold)
STYLE_COLOURS: dict[str, tuple[str, bool]] = {
    text.TEXT: (_colour("TEXT"), False),
    text.MUTED: (_colour("MUTED"), False),
    text.BOLD: (_colour("INK"), True),
    text.ACCENT: (_colour("LEAF"), False),
    text.INFO: (_colour("OCEAN"), False),
    text.SUCCESS: (_colour("SUCCESS"), False),
    text.WARNING: (WARNING.get(palette.THEME, WARNING["light"]), False),
    text.ERROR: (_colour("ERROR"), False),
    text.HEADING: (_colour("INK"), True),
    text.COMMAND: (_colour("INK"), True),
    text.PROMPT_USER: (_colour("LEAF"), True),
    text.PROMPT_PATH: (_colour("OCEAN"), True),
}


def char_formats() -> dict[str, QTextCharFormat]:
    """A text format for every style."""
    formats = {}
    for style, (colour, bold) in STYLE_COLOURS.items():
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colour))
        fmt.setFontWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
        formats[style] = fmt
    return formats


def monospace_font() -> QFont:
    """The first installed font of ``FONT_FAMILIES``, else the system's fixed-width font."""
    installed = set(QFontDatabase.families())
    for family in FONT_FAMILIES:
        if family in installed:
            font = QFont(family, FONT_POINT_SIZE)
            break
    else:
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(FONT_POINT_SIZE)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setFixedPitch(True)
    return font
