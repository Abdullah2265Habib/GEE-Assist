"""Colour palettes of the app's themes, in one place.

``theme`` and ``form_theme`` take their colours from ``ACTIVE``. The names come from
the light theme: ``WHITE`` is the colour of cards and surfaces, ``INK`` the strongest
text, ``LEAF`` / ``OCEAN`` the green and blue accents; a dark palette gives each name
its dark-theme colour.
"""

from __future__ import annotations

LIGHT: dict[str, str] = {
    # surfaces and text
    "WHITE": "#FFFFFF",
    "INK": "#1E3A3A",            # headings / main text: deep green-slate
    "TEXT": "#34504F",
    "MUTED": "#6B8582",
    "SUBTLE": "#93A9A6",
    "BORDER": "#D3E4DF",
    "BORDER_STRONG": "#B9D3CC",
    "BORDER_HOVER": "#9CC5BA",
    "FIELD_BG": "#FBFDFC",
    "DISABLED_BG": "#F3F6F5",
    # accents
    "LEAF": "#2E9E78",           # primary green
    "LEAF_DARK": "#237D60",
    "OCEAN": "#2F7FC1",          # primary blue
    "OCEAN_DARK": "#24659C",
    "MINT": "#EAF6F0",
    "SKY": "#E6F1FA",
    "FOAM": "#F4FAF8",
    # pages and section headers
    "PAGE_BG": "#F2F8F6",        # soft green-blue page behind the white cards
    "HEADER_GREEN": "#DFF1E8",   # section header band: light sage-green ...
    "HEADER_BLUE": "#DFEDF7",    # ... fading to a light sky-blue
    "HEADER_LINE": "#C4E0D5",
    # messages
    "ERROR": "#C0392B",
    "ERROR_BG": "#FDF1EF",
    "SUCCESS": "#23845E",
    "SUCCESS_BG": "#ECF7F1",
    "INFO_BG": "#EEF5FB",
    "ERROR_BORDER": "#F3C9C3",
    "SUCCESS_BORDER": "#BFE3D1",
    "INFO_BORDER": "#C9DFF1",
    "ERROR_FIELD_BG": "#FFFBFA",   # a field with an invalid value
    # primary (gradient) buttons
    "PRIMARY_TEXT": "#FFFFFF",
    "PRIMARY_DISABLED_TEXT": "#F2F7F6",
    "PRIMARY_DISABLED_FROM": "#8CCBB6",
    "PRIMARY_DISABLED_TO": "#92BCE0",
    "OPEN_BUTTON_TOP": "#4CB98E",  # "open folder" button: gradient into LEAF
    # signed-in pages: background gradient
    "PAGE_GRADIENT_TOP": "#F3FAF6",
    "PAGE_GRADIENT_MIDDLE": "#F2F8FB",
    "PAGE_GRADIENT_BOTTOM": "#ECF4FB",
    # sign-in picture panel: background gradient
    "HERO_TOP": "#EEF8F2",
    "HERO_MIDDLE": "#EAF4F8",
    "HERO_BOTTOM": "#E2EEF9",
    # pieces of particular screens
    "TILE_DISABLED_BG": "#FAFCFB",  # "coming soon" dashboard cards
    "PROGRESS_TRACK": "#E4EEEB",
    "PROGRESS_PAUSED": "#9DB8B2",
    "PROGRESS_FAILED": "#E3A79F",
    "TABLE_LINE": "#EDF3F1",
    "CHART_GRID": "#E3EEEA",
    "SHADOW": "#1E5A57",
    "SPLASH_BG": "#FFFFFF",         # the intro video has a white background in every theme
}

ACTIVE: dict[str, str] = LIGHT
