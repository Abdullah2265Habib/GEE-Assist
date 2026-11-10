"""Menu bar along the top of the signed-in window, like the classic one in Word or Excel.

File, Edit, View, Options and Help, each with keyboard shortcuts shown next to its
items. The Edit commands act on the text field that has the cursor, as in Word;
items that cannot apply are greyed out while the menu is open. The other actions
are given their meaning by the window the menu bar belongs to (see ``HomeWindow``).
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence
from PyQt6.QtWidgets import QApplication, QComboBox, QLineEdit, QMenu, QMenuBar, QPlainTextEdit, QTextEdit, QWidget

from frontend import appearance, palette, theme

STYLESHEET = f"""
QMenuBar {{
    background: {theme.WHITE}; border: none; border-bottom: 1px solid {theme.BORDER};
    padding: 2px 6px; color: {theme.INK};
}}
QMenuBar::item {{ background: transparent; padding: 5px 12px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {theme.FOAM}; }}
QMenuBar::item:pressed {{ background: {theme.MINT}; }}
""" + theme.MENU_STYLE


class AppMenuBar(QMenuBar):
    theme_chosen = pyqtSignal(str)  # a theme other than the current one, e.g. "dark-green"

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(STYLESHEET)

        self.file_menu = self._menu("&File")
        self.new_request = self._action(self.file_menu, "&New request", "Ctrl+N")
        self.file_menu.addSeparator()
        self.sign_out = self._action(self.file_menu, "Sign &out")
        self.exit = self._action(self.file_menu, "E&xit", "Ctrl+Q")

        self.edit_menu = self._menu("&Edit")
        self.undo = self._action(self.edit_menu, "&Undo", QKeySequence.StandardKey.Undo)
        self.redo = self._action(self.edit_menu, "&Redo", "Ctrl+Y")
        self.edit_menu.addSeparator()
        self.cut = self._action(self.edit_menu, "Cu&t", QKeySequence.StandardKey.Cut)
        self.copy = self._action(self.edit_menu, "&Copy", QKeySequence.StandardKey.Copy)
        self.paste = self._action(self.edit_menu, "&Paste", QKeySequence.StandardKey.Paste)
        self.edit_menu.addSeparator()
        self.select_all = self._action(self.edit_menu, "Select &all", QKeySequence.StandardKey.SelectAll)
        self._edit_commands = {
            self.undo: "undo", self.redo: "redo", self.cut: "cut",
            self.copy: "copy", self.paste: "paste", self.select_all: "selectAll",
        }
        for action, command in self._edit_commands.items():
            action.triggered.connect(lambda _=False, command=command: self._run_edit(command))
        self.edit_menu.aboutToShow.connect(self._update_edit_items)
        self.edit_menu.aboutToHide.connect(self._enable_edit_items)  # shortcuts keep working afterwards

        self.view_menu = self._menu("&View")
        self.view_dashboard = self._action(self.view_menu, "&Dashboard", "Ctrl+1")
        self.view_query_input = self._action(self.view_menu, "&Query Input", "Ctrl+2")
        self.view_downloads = self._action(self.view_menu, "Do&wnloads", "Ctrl+3")
        self.view_account = self._action(self.view_menu, "&Account", "Ctrl+4")
        self.view_menu.addSeparator()
        self.toggle_side_bar = self._action(self.view_menu, "&Side bar", "Ctrl+B", checkable=True)
        self.toggle_terminal = self._action(self.view_menu, "&Terminal", "Ctrl+`", checkable=True)
        self.full_screen = self._action(self.view_menu, "&Full screen", "F11", checkable=True)
        self.view_menu.addSeparator()
        self.theme_menu = self.view_menu.addMenu("&Theme")
        self.theme_menu.setStyleSheet(theme.MENU_STYLE)
        self.theme_actions: dict[str, QAction] = {}
        group = QActionGroup(self)  # one theme at a time
        for name, label in appearance.THEMES.items():
            action = self._action(self.theme_menu, label, checkable=True)
            action.setChecked(name == palette.THEME)
            action.triggered.connect(lambda _=False, name=name: self._choose_theme(name))
            group.addAction(action)
            self.theme_actions[name] = action

        self.options_menu = self._menu("&Options")
        self.chunk_size = self._action(self.options_menu, "Download &chunk size…")
        self.manage_users = self._action(self.options_menu, "&Manage users…")

        self.help_menu = self._menu("&Help")
        self.about = self._action(self.help_menu, "&About GEE-Assist")

    # ------------------------------------------------------------- Theme
    def _choose_theme(self, name: str) -> None:
        if name != palette.THEME:
            self.theme_chosen.emit(name)

    def show_current_theme(self) -> None:
        """Tick the theme in use again (e.g. when switching was cancelled)."""
        self.theme_actions[palette.THEME].setChecked(True)

    # ------------------------------------------------------------- Edit
    @staticmethod
    def edit_target() -> QWidget | None:
        """The text field the Edit commands apply to: the one with the cursor, if any."""
        widget = QApplication.focusWidget()
        if isinstance(widget, QComboBox) and widget.isEditable():
            widget = widget.lineEdit()
        return widget if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit)) else None

    def _run_edit(self, command: str) -> None:
        target = self.edit_target()
        if target is not None:
            getattr(target, command)()

    def _update_edit_items(self) -> None:
        target = self.edit_target()
        if target is None:
            for action in self._edit_commands:
                action.setEnabled(False)
            return
        writable = not target.isReadOnly()
        if isinstance(target, QLineEdit):
            selected = target.hasSelectedText()
            can_undo, can_redo = target.isUndoAvailable(), target.isRedoAvailable()
            can_paste = bool(QApplication.clipboard().text())
        else:
            selected = target.textCursor().hasSelection()
            document = target.document()
            can_undo, can_redo = document.isUndoAvailable(), document.isRedoAvailable()
            can_paste = target.canPaste()
        self.undo.setEnabled(writable and can_undo)
        self.redo.setEnabled(writable and can_redo)
        self.cut.setEnabled(writable and selected)
        self.copy.setEnabled(selected)
        self.paste.setEnabled(writable and can_paste)
        self.select_all.setEnabled(True)

    def _enable_edit_items(self) -> None:
        for action in self._edit_commands:
            action.setEnabled(True)

    def _menu(self, title: str) -> QMenu:
        menu = self.addMenu(title)
        menu.setStyleSheet(theme.MENU_STYLE)
        return menu

    def _action(self, menu: QMenu, text: str, shortcut=None, checkable: bool = False) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        menu.addAction(action)
        return action
