"""Vertical navigation bar on the left of the signed-in window.

The bar slides between two widths when its logo is clicked. Expanded, its buttons
show their full names ("Downloads"); collapsed, only a short label ("D").
Any widget added with a ``set_compact(bool)`` method follows the same switch.

Sliding open, the names appear first and are uncovered as the bar widens; sliding
closed, they are covered first and switch to the short labels at the end.
"""

from __future__ import annotations

from PyQt6.QtCore import QAbstractAnimation, QEasingCurve, QSize, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QFrame, QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from frontend import theme

COLLAPSED_WIDTH = 76
EXPANDED_WIDTH = 220
SLIDE_MS = 220
LOGO_SIZE = 48

STYLESHEET = f"""
#SideBar {{ background: {theme.WHITE}; border: none; border-right: 1px solid {theme.BORDER}; }}
QToolButton#SideLogo {{ border: none; background: transparent; padding: 0; }}
QPushButton#SideButton {{
    border: none; border-radius: 8px; background: transparent; color: {theme.INK};
    font-weight: 600; text-align: left; padding: 0 14px;
}}
QPushButton#SideButton[compact="true"] {{ text-align: center; padding: 0; }}
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
        self.setFixedHeight(40)
        # Narrower than its text while the bar slides: the text is clipped, not the bar held open.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def set_compact(self, compact: bool) -> None:
        self.setText(self.short_text if compact else self.full_text)
        self.setProperty("compact", compact)
        self.style().unpolish(self)
        self.style().polish(self)


class SideBar(QFrame):
    expanded_changed = pyqtSignal(bool)

    def __init__(self, logo: QPixmap, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SideBar")
        self.setStyleSheet(STYLESHEET)
        self._expanded = True
        self._compact_widgets: list[QWidget] = []

        self.logo = QToolButton(objectName="SideLogo")
        self.logo.setIcon(QIcon(logo))
        self.logo.setIconSize(QSize(LOGO_SIZE, LOGO_SIZE))
        self.logo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logo.clicked.connect(self.toggle)

        self._items = QVBoxLayout()
        self._items.setSpacing(4)
        self._footer = QVBoxLayout()
        self._footer.setSpacing(6)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 18, 12, 18)
        layout.setSpacing(18)
        layout.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addLayout(self._items)
        layout.addStretch(1)
        layout.addLayout(self._footer)

        self.setFixedWidth(EXPANDED_WIDTH)
        self._slide = QVariantAnimation(self)
        self._slide.setDuration(SLIDE_MS)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide.valueChanged.connect(lambda width: self.setFixedWidth(int(width)))
        self._slide.finished.connect(self._slide_finished)
        self._update_logo_tip()

    # ------------------------------------------------------------- contents
    def add_button(self, text: str, short: str, footer: bool = False) -> SideButton:
        button = SideButton(text, short)
        self.add_widget(button, footer)
        return button

    def add_widget(self, widget: QWidget, footer: bool = False) -> None:
        """Add ``widget`` under the logo, or at the bottom of the bar with ``footer``."""
        (self._footer if footer else self._items).addWidget(widget)
        if hasattr(widget, "set_compact"):
            self._compact_widgets.append(widget)
            widget.set_compact(not self._expanded)

    # ------------------------------------------------------------- sliding
    def is_expanded(self) -> bool:
        return self._expanded

    def is_sliding(self) -> bool:
        return self._slide.state() == QAbstractAnimation.State.Running

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
            self._slide.setStartValue(self.width())
            self._slide.setEndValue(target)
            self._slide.start()
        else:
            self.setFixedWidth(target)
            self._slide_finished()
        self._update_logo_tip()
        self.expanded_changed.emit(expanded)

    def _slide_finished(self) -> None:
        if not self._expanded:
            self._set_compact(True)  # short labels once the bar is narrow

    def _set_compact(self, compact: bool) -> None:
        for widget in self._compact_widgets:
            widget.set_compact(compact)

    def _update_logo_tip(self) -> None:
        self.logo.setToolTip("Collapse the side bar" if self._expanded else "Expand the side bar")
