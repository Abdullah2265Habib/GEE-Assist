"""Colour palettes of the app's themes (light, dark blue-green, dark grey), in one place.

``theme`` and ``form_theme`` take their colours from ``ACTIVE``, the saved theme's
palette. The names come from the light theme: ``WHITE`` is the colour of cards and
surfaces, ``INK`` the strongest text, ``LEAF`` / ``OCEAN`` the green and blue accents;
a dark palette gives each name its dark-theme colour.
"""

from __future__ import annotations

import os

from frontend import appearance

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


# Dark themes: dark surfaces with light, high-contrast text, borders and accents.
# Gradient (primary) buttons use the light accents with dark text on them.
DARK_GREEN: dict[str, str] = {   # deep blue-green
    "WHITE": "#173235",
    "INK": "#EAF7F3",
    "TEXT": "#CFE5E0",
    "MUTED": "#A3C2BC",
    "SUBTLE": "#80A39D",
    "BORDER": "#2B4D4E",
    "BORDER_STRONG": "#3F6866",
    "BORDER_HOVER": "#5E8C88",
    "FIELD_BG": "#12292B",
    "DISABLED_BG": "#1C3436",
    "LEAF": "#5ED3A8",
    "LEAF_DARK": "#86E3C1",
    "OCEAN": "#6CB8F0",
    "OCEAN_DARK": "#93CCF6",
    "MINT": "#21403F",
    "SKY": "#1C3448",
    "FOAM": "#1E3B3C",
    "PAGE_BG": "#0F2224",
    "HEADER_GREEN": "#1D3D39",
    "HEADER_BLUE": "#1B3445",
    "HEADER_LINE": "#2F5552",
    "ERROR": "#FF8F80",
    "ERROR_BG": "#3A2224",
    "SUCCESS": "#72DFB2",
    "SUCCESS_BG": "#163A2E",
    "INFO_BG": "#172F42",
    "ERROR_BORDER": "#6B3A37",
    "SUCCESS_BORDER": "#2E6650",
    "INFO_BORDER": "#2E5677",
    "ERROR_FIELD_BG": "#2C1E20",
    "PRIMARY_TEXT": "#0B1F21",
    "PRIMARY_DISABLED_TEXT": "#5E7C79",
    "PRIMARY_DISABLED_FROM": "#2B4F47",
    "PRIMARY_DISABLED_TO": "#2B4659",
    "OPEN_BUTTON_TOP": "#86E3C1",
    "PAGE_GRADIENT_TOP": "#0F2426",
    "PAGE_GRADIENT_MIDDLE": "#0F2229",
    "PAGE_GRADIENT_BOTTOM": "#0E1F2B",
    "HERO_TOP": "#12302A",
    "HERO_MIDDLE": "#122B33",
    "HERO_BOTTOM": "#13263A",
    "TILE_DISABLED_BG": "#142A2C",
    "PROGRESS_TRACK": "#24403F",
    "PROGRESS_PAUSED": "#7A9C96",
    "PROGRESS_FAILED": "#D08378",
    "TABLE_LINE": "#22403F",
    "CHART_GRID": "#264544",
    "SHADOW": "#000000",
    "SPLASH_BG": "#FFFFFF",
}

DARK_GREY: dict[str, str] = {    # plain black and grey
    "WHITE": "#1F1F1F",
    "INK": "#F2F2F2",
    "TEXT": "#D9D9D9",
    "MUTED": "#ABABAB",
    "SUBTLE": "#8A8A8A",
    "BORDER": "#333333",
    "BORDER_STRONG": "#4A4A4A",
    "BORDER_HOVER": "#6B6B6B",
    "FIELD_BG": "#181818",
    "DISABLED_BG": "#262626",
    "LEAF": "#6FD6AE",
    "LEAF_DARK": "#95E4C5",
    "OCEAN": "#7DBDF2",
    "OCEAN_DARK": "#A3D0F6",
    "MINT": "#303030",
    "SKY": "#2A2F35",
    "FOAM": "#2A2A2A",
    "PAGE_BG": "#141414",
    "HEADER_GREEN": "#262626",
    "HEADER_BLUE": "#2B2B2B",
    "HEADER_LINE": "#3A3A3A",
    "ERROR": "#FF8A80",
    "ERROR_BG": "#3A2323",
    "SUCCESS": "#7EDDB6",
    "SUCCESS_BG": "#1E3329",
    "INFO_BG": "#1E2A35",
    "ERROR_BORDER": "#663535",
    "SUCCESS_BORDER": "#335C48",
    "INFO_BORDER": "#334D66",
    "ERROR_FIELD_BG": "#2A1F1F",
    "PRIMARY_TEXT": "#111111",
    "PRIMARY_DISABLED_TEXT": "#6E6E6E",
    "PRIMARY_DISABLED_FROM": "#383838",
    "PRIMARY_DISABLED_TO": "#3D3D3D",
    "OPEN_BUTTON_TOP": "#95E4C5",
    "PAGE_GRADIENT_TOP": "#151515",
    "PAGE_GRADIENT_MIDDLE": "#161616",
    "PAGE_GRADIENT_BOTTOM": "#181818",
    "HERO_TOP": "#1B1B1B",
    "HERO_MIDDLE": "#1D1D1D",
    "HERO_BOTTOM": "#202020",
    "TILE_DISABLED_BG": "#1A1A1A",
    "PROGRESS_TRACK": "#2E2E2E",
    "PROGRESS_PAUSED": "#8F8F8F",
    "PROGRESS_FAILED": "#D08A80",
    "TABLE_LINE": "#2C2C2C",
    "CHART_GRID": "#2E2E2E",
    "SHADOW": "#000000",
    "SPLASH_BG": "#FFFFFF",
}

PALETTES = {"light": LIGHT, "dark-green": DARK_GREEN, "dark-grey": DARK_GREY}

# The theme is chosen once, at start-up: the saved choice (``GEE_ASSIST_THEME`` overrides it,
# e.g. for the tests). Changing it takes effect the next time the app starts.
_override = os.environ.get("GEE_ASSIST_THEME")
THEME: str = _override if _override in PALETTES else appearance.current_theme()
ACTIVE: dict[str, str] = PALETTES[THEME]
IS_DARK: bool = THEME != "light"
