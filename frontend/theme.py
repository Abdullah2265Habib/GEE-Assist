"""GEE-Assist light classical theme: white surfaces, earth greens and sky blues, serif headings."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QApplication

# ----------------------------------------------------------------------------- palette
WHITE = "#FFFFFF"
INK = "#1E3A3A"            # headings / main text: deep green-slate
TEXT = "#34504F"
MUTED = "#6B8582"
SUBTLE = "#93A9A6"
BORDER = "#D3E4DF"
BORDER_STRONG = "#B9D3CC"
FIELD_BG = "#FBFDFC"

LEAF = "#2E9E78"           # primary green
LEAF_DARK = "#237D60"
OCEAN = "#2F7FC1"          # primary blue
OCEAN_DARK = "#24659C"
MINT = "#EAF6F0"
SKY = "#E6F1FA"
FOAM = "#F4FAF8"

ERROR = "#C0392B"
ERROR_BG = "#FDF1EF"
SUCCESS = "#23845E"
SUCCESS_BG = "#ECF7F1"
INFO_BG = "#EEF5FB"

SERIF = "Georgia"
SANS = "Segoe UI"

_ICONS_DIR = Path(__file__).resolve().parent / "resources" / "icons"
CHECK_ICON = (_ICONS_DIR / "check.svg").as_posix()


def color(hex_value: str, alpha: int = 255) -> QColor:
    c = QColor(hex_value)
    c.setAlpha(alpha)
    return c


def heading_font(point_size: int, bold: bool = False) -> QFont:
    font = QFont(SERIF, point_size)
    font.setBold(bold)
    return font


# ----------------------------------------------------------------------------- stylesheet
STYLESHEET = f"""
QWidget {{
    font-family: "{SANS}";
    font-size: 10pt;
    color: {TEXT};
}}
QToolTip {{
    background: {WHITE}; color: {INK}; border: 1px solid {BORDER}; padding: 4px 6px;
}}

/* ---- text ---- */
QLabel#Title {{ font-family: "{SERIF}"; font-size: 23pt; color: {INK}; }}
QLabel#Subtitle {{ color: {MUTED}; font-size: 10.5pt; }}
QLabel#FieldLabel {{ color: {INK}; font-weight: 600; font-size: 9.5pt; }}
QLabel#FieldError {{ color: {ERROR}; font-size: 8.5pt; }}
QLabel#FieldHint {{ color: {SUBTLE}; font-size: 8.5pt; }}
QLabel#Muted {{ color: {MUTED}; }}
QLabel#Divider {{ color: {SUBTLE}; font-size: 9pt; }}

/* ---- banners ---- */
QLabel#ErrorBanner, QLabel#SuccessBanner, QLabel#InfoBanner {{
    border-radius: 8px; padding: 9px 12px; font-size: 9.5pt;
}}
QLabel#ErrorBanner {{ background: {ERROR_BG}; color: {ERROR}; border: 1px solid #F3C9C3; }}
QLabel#SuccessBanner {{ background: {SUCCESS_BG}; color: {SUCCESS}; border: 1px solid #BFE3D1; }}
QLabel#InfoBanner {{ background: {INFO_BG}; color: {OCEAN_DARK}; border: 1px solid #C9DFF1; }}

/* ---- card ---- */
QFrame#AuthCard {{
    background: {WHITE};
    border: 1px solid {BORDER};
    border-radius: 18px;
}}

/* ---- inputs ---- */
QLineEdit {{
    background: {FIELD_BG};
    border: 1px solid {BORDER_STRONG};
    border-radius: 9px;
    padding: 9px 12px;
    font-size: 10.5pt;
    color: {INK};
    selection-background-color: {OCEAN};
}}
QLineEdit:hover {{ border-color: #9CC5BA; }}
QLineEdit:focus {{ border: 1.5px solid {LEAF}; background: {WHITE}; }}
QLineEdit[invalid="true"] {{ border: 1.5px solid {ERROR}; background: #FFFBFA; }}
QLineEdit:disabled {{ color: {SUBTLE}; background: #F3F6F5; }}

QCheckBox {{ color: {TEXT}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {BORDER_STRONG}; background: {WHITE};
}}
QCheckBox::indicator:hover {{ border-color: {LEAF}; }}
QCheckBox::indicator:checked {{
    background: {LEAF}; border-color: {LEAF};
    image: url("{CHECK_ICON}");
}}

/* ---- buttons ---- */
QPushButton {{
    border-radius: 9px; padding: 10px 18px; font-size: 10.5pt; font-weight: 600;
}}
QPushButton#PrimaryButton {{
    color: {WHITE}; border: none;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {LEAF}, stop:1 {OCEAN});
}}
QPushButton#PrimaryButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {LEAF_DARK}, stop:1 {OCEAN_DARK});
}}
QPushButton#PrimaryButton:pressed {{ padding-top: 11px; padding-bottom: 9px; }}
QPushButton#PrimaryButton:disabled {{
    color: #F2F7F6;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8CCBB6, stop:1 #92BCE0);
}}
QPushButton#SecondaryButton {{
    color: {INK}; background: {WHITE}; border: 1px solid {BORDER_STRONG};
}}
QPushButton#SecondaryButton:hover {{ background: {FOAM}; border-color: #9CC5BA; }}
QPushButton#SecondaryButton:pressed {{ background: {MINT}; }}
QPushButton#SecondaryButton:disabled {{ color: {SUBTLE}; border-color: {BORDER}; }}
QPushButton#LinkButton {{
    color: {OCEAN}; background: transparent; border: none; padding: 2px 4px; font-weight: 600;
}}
QPushButton#LinkButton:hover {{ color: {OCEAN_DARK}; text-decoration: underline; }}
QPushButton#LinkButton:disabled {{ color: {SUBTLE}; }}

QProgressBar#BusyBar {{
    background: {MINT}; border: none; border-radius: 2px; max-height: 4px; min-height: 4px;
}}
QProgressBar#BusyBar::chunk {{
    border-radius: 2px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {LEAF}, stop:1 {OCEAN});
}}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER_STRONG}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""

# Pop-up menus (the account menu, the menu bar's menus).
MENU_STYLE = f"""
QMenu {{ background: {WHITE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px; }}
QMenu::item {{ color: {INK}; padding: 8px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {FOAM}; }}
QMenu::item:disabled {{ color: {SUBTLE}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFont(SANS, 10))
    app.setStyleSheet(STYLESHEET)
