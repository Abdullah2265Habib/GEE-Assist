"""Light, classical earth theme (leaf greens, ocean blues) for the query input UI.

The palette matches ``frontend/theme.py`` on the authentication branches so the
parameter form looks like the rest of the app.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

# ----------------------------------------------------------------------------- palette
WHITE = "#FFFFFF"
INK = "#1E3A3A"            # headings / main text: deep green-slate
TEXT = "#34504F"
MUTED = "#6B8582"
SUBTLE = "#93A9A6"
BORDER = "#D3E4DF"
BORDER_STRONG = "#B9D3CC"
BORDER_HOVER = "#9CC5BA"
FIELD_BG = "#FBFDFC"
DISABLED_BG = "#F3F6F5"

LEAF = "#2E9E78"           # primary green
LEAF_DARK = "#237D60"
OCEAN = "#2F7FC1"          # primary blue
OCEAN_DARK = "#24659C"
MINT = "#EAF6F0"
SKY = "#E6F1FA"
FOAM = "#F4FAF8"
PAGE_BG = "#F2F8F6"        # soft green-blue page behind the white cards
HEADER_GREEN = "#DFF1E8"   # section header band: light sage-green ...
HEADER_BLUE = "#DFEDF7"    # ... fading to a light sky-blue
HEADER_LINE = "#C4E0D5"

ERROR = "#C0392B"
SUCCESS = "#23845E"

SERIF = "Georgia"
SANS = "Segoe UI"

_ICONS = Path(__file__).resolve().parent / "resources" / "icons"
CHECK_ICON = (_ICONS / "check.svg").as_posix()
CHECK_GREEN_ICON = (_ICONS / "check_green.svg").as_posix()
CHEVRON_UP_WHITE = (_ICONS / "chevron_up_white.svg").as_posix()
CHEVRON_DOWN = (_ICONS / "chevron_down.svg").as_posix()
CHEVRON_UP = (_ICONS / "chevron_up.svg").as_posix()


def apply_light_mode(app: QApplication) -> None:
    """Keep the app light even when Windows is in dark mode.

    Fusion follows the system colour scheme, which is what turned the form dark.
    """
    app.setStyle("Fusion")
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)

    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: PAGE_BG,
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: WHITE,
        QPalette.ColorRole.AlternateBase: FOAM,
        QPalette.ColorRole.Text: INK,
        QPalette.ColorRole.Button: WHITE,
        QPalette.ColorRole.ButtonText: INK,
        QPalette.ColorRole.Highlight: LEAF,
        QPalette.ColorRole.HighlightedText: WHITE,
        QPalette.ColorRole.ToolTipBase: WHITE,
        QPalette.ColorRole.ToolTipText: INK,
        QPalette.ColorRole.PlaceholderText: SUBTLE,
        QPalette.ColorRole.Link: OCEAN,
        QPalette.ColorRole.Light: WHITE,
        QPalette.ColorRole.Midlight: FOAM,
        QPalette.ColorRole.Mid: BORDER_STRONG,
        QPalette.ColorRole.Dark: BORDER_HOVER,
        QPalette.ColorRole.Shadow: MUTED,
    }
    for role, value in roles.items():
        p.setColor(role, QColor(value))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(SUBTLE))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(DISABLED_BG))
    app.setPalette(p)


# ----------------------------------------------------------------------------- stylesheet
FIELDS = "QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit"

FORM_STYLESHEET = f"""
#ParameterForm, #ParameterFormContent {{ background: {PAGE_BG}; }}
#ParameterForm QWidget {{ font-family: "{SANS}"; font-size: 10pt; color: {TEXT}; }}
QToolTip {{ background: {WHITE}; color: {INK}; border: 1px solid {BORDER}; padding: 4px 6px; }}

/* ---- section cards: tinted header band with the heading, white body below ---- */
QFrame#SectionCard {{
    background: {WHITE};
    border: 1px solid {BORDER_STRONG};
    border-radius: 12px;
}}
QFrame#SectionCard QWidget {{ background: transparent; }}
#ParameterForm QFrame#SectionHeader {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {HEADER_GREEN}, stop:1 {HEADER_BLUE});
    border: none;
    border-bottom: 1px solid {HEADER_LINE};
    border-top-left-radius: 11px;
    border-top-right-radius: 11px;
}}
#ParameterForm QLabel#SectionTitle {{
    font-family: "{SERIF}";
    font-size: 13.5pt;
    font-weight: bold;
    color: {INK};
    background: transparent;
}}

/* ---- text ---- */
QLabel {{ color: {TEXT}; background: transparent; }}
QRadioButton {{ color: {INK}; spacing: 7px; }}
QRadioButton::indicator {{
    width: 14px; height: 14px; border-radius: 8px;
    border: 1px solid {BORDER_STRONG}; background: {WHITE};
}}
QRadioButton::indicator:hover {{ border-color: {LEAF}; }}
QRadioButton::indicator:checked {{
    border-color: {LEAF};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                                stop:0 {LEAF}, stop:0.45 {LEAF}, stop:0.55 {WHITE}, stop:1 {WHITE});
}}

/* ---- inputs ---- */
{FIELDS} {{
    background: {FIELD_BG};
    color: {INK};
    border: 1px solid {BORDER_STRONG};
    border-radius: 7px;
    padding: 5px 9px;
    min-height: 20px;
    selection-background-color: {OCEAN};
    selection-color: {WHITE};
}}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QDateEdit:hover {{ border-color: {BORDER_HOVER}; }}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
    border: 1px solid {LEAF}; background: {WHITE};
}}
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QDateEdit:disabled {{
    color: {SUBTLE}; background: {DISABLED_BG}; border-color: {BORDER};
}}
QComboBox::drop-down, QDateEdit::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right;
    width: 24px; border: none;
}}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url("{CHEVRON_DOWN}"); width: 12px; height: 12px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; width: 20px; border: none; background: transparent;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-position: top right; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-position: bottom right; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background: {MINT}; border-radius: 4px; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{CHEVRON_UP}"); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{CHEVRON_DOWN}"); width: 10px; height: 10px; }}

QComboBox QAbstractItemView {{
    background: {WHITE};
    color: {INK};
    border: 1px solid {BORDER_STRONG};
    selection-background-color: {MINT};
    selection-color: {INK};
    outline: none;
}}

/* ---- check lists (bands, processes) ---- */
QListWidget {{
    background: {FIELD_BG};
    border: 1px solid {BORDER_STRONG};
    border-radius: 8px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{ color: {INK}; padding: 4px 6px; border-radius: 5px; }}
QListWidget::item:hover {{ background: {FOAM}; }}
QListWidget::item:selected {{ background: {MINT}; color: {INK}; }}
QListWidget::item:disabled {{ color: {SUBTLE}; }}
QListWidget::indicator {{
    width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid {BORDER_STRONG}; background: {WHITE};
}}
QListWidget::indicator:hover {{ border-color: {LEAF}; }}
QListWidget::indicator:checked {{ background: {LEAF}; border-color: {LEAF}; image: url("{CHECK_ICON}"); }}
QListWidget::indicator:disabled {{ background: {DISABLED_BG}; border-color: {BORDER}; }}

/* ---- calendar popup ---- */
QCalendarWidget QWidget {{ alternate-background-color: {FOAM}; }}
QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {MINT}; }}
QCalendarWidget QToolButton {{ color: {INK}; background: transparent; padding: 4px 8px; border-radius: 6px; }}
QCalendarWidget QToolButton:hover {{ background: {WHITE}; }}
QCalendarWidget QAbstractItemView {{
    background: {WHITE}; color: {INK};
    selection-background-color: {LEAF}; selection-color: {WHITE};
}}
QCalendarWidget QAbstractItemView:disabled {{ color: {SUBTLE}; }}

/* ---- buttons ---- */
QPushButton {{
    border-radius: 8px; padding: 7px 16px; font-weight: 600;
    color: {INK}; background: {WHITE}; border: 1px solid {BORDER_STRONG};
}}
QPushButton:hover {{ background: {FOAM}; border-color: {BORDER_HOVER}; }}
QPushButton:pressed {{ background: {MINT}; }}
QPushButton:disabled {{ color: {SUBTLE}; border-color: {BORDER}; }}
QPushButton#PrimaryButton {{
    color: {WHITE}; border: none; padding: 8px 20px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {LEAF}, stop:1 {OCEAN});
}}
QPushButton#PrimaryButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {LEAF_DARK}, stop:1 {OCEAN_DARK});
}}

/* ---- bottom action bar ---- */
#FormActionBar {{ background: {WHITE}; border-top: 1px solid {BORDER}; }}

/* ---- scrolling ---- */
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER_STRONG}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {BORDER_HOVER}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""


# ----------------------------------------------------------------------------- main window
# Only targeted selectors here: this cascades into every page of the window.
MAIN_WINDOW_STYLESHEET = f"""
QStatusBar {{
    background: {WHITE};
    border-top: 1px solid {BORDER};
    color: {MUTED};
    min-height: 40px;
}}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel#ModeCaption {{ color: {MUTED}; padding-right: 2px; }}

QToolButton#ModeSwitcher {{
    color: {WHITE};
    font-weight: 600;
    padding: 6px 16px;
    margin: 4px 10px 4px 4px;
    border: none;
    border-radius: 8px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {LEAF}, stop:1 {OCEAN});
}}
QToolButton#ModeSwitcher:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {LEAF_DARK}, stop:1 {OCEAN_DARK});
}}

QMenu#ModeMenu {{
    background: {WHITE};
    border: 1px solid {BORDER_STRONG};
    border-radius: 10px;
    padding: 6px;
}}
QMenu#ModeMenu::item {{
    color: {INK};
    padding: 8px 18px 8px 30px;
    border-radius: 6px;
}}
QMenu#ModeMenu::item:selected {{ background: {MINT}; }}
QMenu#ModeMenu::item:checked {{ color: {LEAF_DARK}; font-weight: 600; }}
QMenu#ModeMenu::indicator {{ width: 14px; height: 14px; left: 8px; }}
QMenu#ModeMenu::indicator:checked, QMenu#ModeMenu::indicator:exclusive:checked {{ image: url("{CHECK_GREEN_ICON}"); }}
"""
