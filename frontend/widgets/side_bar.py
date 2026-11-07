"""Vertical navigation bar on the left of the signed-in window.

The bar slides between two widths when its logo is clicked. Expanded, its buttons
show their full names ("Downloads"); collapsed, only a short label ("D"). It starts
collapsed unless created with ``expanded=True``. A round back button sits above
the logo; the bar's owner decides where it leads and, with ``show_back``, when it shows.
Without it, the logo moves up to the top of the bar.
Any widget added with a ``set_compact(bool)`` method follows the same switch.

Sliding open, the names appear first and are uncovered as the bar widens; sliding
closed, they are covered first and switch to the short labels at the end.

The slide is driven by a plain timer and a clock rather than a Qt animation: Qt
WebEngine (used by the sign-in screen and the map) can leave Qt's animation timing
stopped after its window closes, which would freeze the bar half-way.
"""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QElapsedTimer, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QWIDGETSIZE_MAX,
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from frontend import theme

LOGO_SIZE = 64
SIDE_MARGIN = 6
BORDER = 1        # the line on the bar's right edge
COLLAPSED_WIDTH = LOGO_SIZE + 2 * SIDE_MARGIN + BORDER   # just wide enough for the logo
EXPANDED_WIDTH = 220
SLIDE_MS = 220
FRAME_MS = 15     # about 60 frames a second
BUTTON_HEIGHT = 40  # collapsed, a button is as wide as it is high: a circle

STYLESHEET = f"""
#SideBar {{ background: {theme.WHITE}; border: none; border-right: {BORDER}px solid {theme.BORDER}; }}
QToolButton#SideLogo {{ border: none; background: transparent; padding: 0; }}
QToolButton#SideBack {{
    border: none; border-radius: {BUTTON_HEIGHT // 2}px; background: transparent;
    color: {theme.INK}; font-size: 15pt; padding: 0;
}}
QToolButton#SideBack:hover {{ background: {theme.FOAM}; }}
QToolButton#SideBack:pressed {{ background: {theme.MINT}; }}
QPushButton#SideButton {{
    border: none; border-radius: 8px; background: transparent; color: {theme.INK};
    font-weight: 600; text-align: left; padding: 0 14px;
}}
QPushButton#SideButton[compact="true"] {{ text-align: center; padding: 0; border-radius: {BUTTON_HEIGHT // 2}px; }}
QPushButton#SideButton:hover {{ background: {theme.FOAM}; }}
QPushButton#SideButton:pressed {{ background: {theme.MINT}; }}
"""


class SideButton(QPushButton):
    """A navigation button: its full name when the bar is expanded, a short label when collapsed."""

    def __init__(self, text: str, short: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.full_text, self.short_text = text, short
        self.setObjectName("SideButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(text)
        self.setFixedHeight(BUTTON_HEIGHT)
        # Narrower than its text while the bar slides: the text is clipped, not the bar held open.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def set_compact(self, compact: bool) -> None:
        self.setText(self.short_text if compact else self.full_text)
        if compact:
            self.setFixedWidth(BUTTON_HEIGHT)
        else:
            self.setMinimumWidth(0)
            self.setMaximumWidth(QWIDGETSIZE_MAX)
        self.setProperty("compact", compact)
        self.style().unpolish(self)
        self.style().polish(self)


class SideBar(QFrame):
    expanded_changed = pyqtSignal(bool)

    def __init__(self, logo: QPixmap, parent: QWidget | None = None, expanded: bool = False):
        super().__init__(parent)
        self.setObjectName("SideBar")
        self.setStyleSheet(STYLESHEET)
        self._expanded = expanded
        self._compact_widgets: list[QWidget] = []
        self._layout_of: dict[QWidget, QBoxLayout] = {}

        self.logo = QToolButton(objectName="SideLogo")
        self.logo.setIcon(QIcon(logo))
        self.logo.setIconSize(QSize(LOGO_SIZE, LOGO_SIZE))
        self.logo.setFixedSize(LOGO_SIZE, LOGO_SIZE)  # exactly the icon, so the circles line up under it
        self.logo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logo.clicked.connect(self.toggle)

        self.back_button = QToolButton(objectName="SideBack")
        self.back_button.setText("←")
        self.back_button.setToolTip("Back")
        self.back_button.setFixedSize(BUTTON_HEIGHT, BUTTON_HEIGHT)
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        back_row = QHBoxLayout()  # centred above the logo, like the circles below it
        back_row.setContentsMargins((LOGO_SIZE - BUTTON_HEIGHT) // 2, 0, 0, 0)
        back_row.addWidget(self.back_button)
        back_row.addStretch(1)

        self._items = QVBoxLayout()
        self._items.setSpacing(4)
        self._footer = QVBoxLayout()
        self._footer.setSpacing(6)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SIDE_MARGIN, 18, SIDE_MARGIN, 18)
        layout.setSpacing(18)
        layout.addLayout(back_row)
        layout.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignLeft)  # stays put while the bar slides
        layout.addLayout(self._items)
        layout.addStretch(1)
        layout.addLayout(self._footer)

        width = EXPANDED_WIDTH if expanded else COLLAPSED_WIDTH
        self.setFixedWidth(width)
        self._slide = QTimer(self)
        self._slide.setInterval(FRAME_MS)
        self._slide.timeout.connect(self._slide_step)
        self._slide_clock = QElapsedTimer()
        self._slide_from = self._slide_to = width
        self._easing = QEasingCurve(QEasingCurve.Type.OutCubic)
        self._update_logo_tip()

    # ------------------------------------------------------------- contents
    def add_button(self, text: str, short: str, footer: bool = False) -> SideButton:
        button = SideButton(text, short)
        self.add_widget(button, footer)
        return button

    def add_widget(self, widget: QWidget, footer: bool = False) -> None:
        """Add ``widget`` under the logo, or at the bottom of the bar with ``footer``."""
        layout = self._footer if footer else self._items
        layout.addWidget(widget)
        self._layout_of[widget] = layout
        if hasattr(widget, "set_compact"):
            self._compact_widgets.append(widget)
            self._apply_compact(widget, not self._expanded)

    def show_back(self, show: bool) -> None:
        """Show or hide the back button above the logo."""
        self.back_button.setVisible(show)

    # ------------------------------------------------------------- sliding
    def is_expanded(self) -> bool:
        return self._expanded

    def is_sliding(self) -> bool:
        return self._slide.isActive()

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self._slide.stop()
        target = EXPANDED_WIDTH if expanded else COLLAPSED_WIDTH
        if expanded:
            self._set_compact(False)  # the names are uncovered as the bar widens
        if animate and self.isVisible():
            self._slide_from, self._slide_to = self.width(), target
            self._slide_clock.start()
            self._slide.start()
        else:
            self.setFixedWidth(target)
            self._slide_finished()
        self._update_logo_tip()
        self.expanded_changed.emit(expanded)

    def _slide_step(self) -> None:
        progress = min(1.0, self._slide_clock.elapsed() / SLIDE_MS)
        eased = self._easing.valueForProgress(progress)
        self.setFixedWidth(round(self._slide_from + (self._slide_to - self._slide_from) * eased))
        if progress >= 1.0:
            self._slide.stop()
            self._slide_finished()

    def _slide_finished(self) -> None:
        if not self._expanded:
            self._set_compact(True)  # short labels once the bar is narrow

    def _set_compact(self, compact: bool) -> None:
        for widget in self._compact_widgets:
            self._apply_compact(widget, compact)

    def _apply_compact(self, widget: QWidget, compact: bool) -> None:
        widget.set_compact(compact)
        if isinstance(widget, SideButton):  # the circle sits under the logo; full names fill the row
            centre = Qt.AlignmentFlag.AlignHCenter if compact else Qt.AlignmentFlag(0)
            self._layout_of[widget].setAlignment(widget, centre)

    def _update_logo_tip(self) -> None:
        self.logo.setToolTip("Collapse the side bar" if self._expanded else "Expand the side bar")
