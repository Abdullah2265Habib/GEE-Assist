"""Bottom-right button that switches between the input modes through a drop-up menu."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PyQt6.QtWidgets import QMenu, QToolButton, QWidget

from frontend import form_theme as theme


class ModeSwitcher(QToolButton):
    """Shows the current mode; clicking opens a menu *above* the button (drop-up).

    Keyboard shortcuts work once the owning window adds ``mode_actions()``
    (``window.addActions(...)``).
    """

    mode_changed = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ModeSwitcher")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)  # chevron on the right of the text
        self.setIcon(QIcon(theme.CHEVRON_UP_WHITE))
        self.setIconSize(QSize(12, 12))

        self._menu = QMenu(self)
        self._menu.setObjectName("ModeMenu")
        self._menu.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._group = QActionGroup(self)
        self._group.setExclusive(True)
        self._names: list[str] = []
        self._current = -1

        self.clicked.connect(self._open_menu)

    def add_mode(self, name: str, description: str = "", shortcut: str = "") -> None:
        index = len(self._names)
        self._names.append(name)
        action = QAction(name, self)
        action.setCheckable(True)
        action.setToolTip(description)
        action.setStatusTip(description)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        action.triggered.connect(lambda _checked=False, i=index: self.set_current(i))
        self._group.addAction(action)
        self._menu.addAction(action)
        if self._current < 0:
            self.set_current(index)
        self._fit_longest_name()

    def _fit_longest_name(self) -> None:
        """Keep the button the same width whichever mode is shown."""
        shown = self.text()
        widths = []
        for name in self._names:
            self.setText(name)
            widths.append(self.sizeHint().width())
        self.setText(shown)
        self.setMinimumWidth(max(widths))

    def mode_actions(self) -> list[QAction]:
        return self._group.actions()

    def current(self) -> int:
        return self._current

    def set_current(self, index: int) -> None:
        if not 0 <= index < len(self._names):
            return
        self._group.actions()[index].setChecked(True)
        self.setText(self._names[index])
        if index != self._current:
            self._current = index
            self.mode_changed.emit(index)

    def _open_menu(self) -> None:
        self._menu.setMinimumWidth(self.width())
        self._menu.popup(self.mapToGlobal(QPoint(0, 0)))
        # The real size is only known once the menu is shown: right-align it with
        # the button and sit it just above.
        button_top_right = self.mapToGlobal(QPoint(self.width(), 0))
        self._menu.move(button_top_right.x() - self._menu.width(), button_top_right.y() - self._menu.height() - 4)
