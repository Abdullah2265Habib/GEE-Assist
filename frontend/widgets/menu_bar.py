"""Menu bar along the top of the signed-in window, like the classic one in Word or Excel.

File, Edit, View, Options and Help, each with keyboard shortcuts shown next to its
items. The menu bar only holds the actions; the window it belongs to decides what
they do (see ``HomeWindow``).
"""

from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenu, QMenuBar, QWidget

from frontend import theme

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

        self.view_menu = self._menu("&View")
        self.view_dashboard = self._action(self.view_menu, "&Dashboard", "Ctrl+1")
        self.view_query_input = self._action(self.view_menu, "&Query Input", "Ctrl+2")
        self.view_downloads = self._action(self.view_menu, "Do&wnloads", "Ctrl+3")
        self.view_account = self._action(self.view_menu, "&Account", "Ctrl+4")
        self.view_menu.addSeparator()
        self.toggle_side_bar = self._action(self.view_menu, "&Side bar", "Ctrl+B", checkable=True)
        self.full_screen = self._action(self.view_menu, "&Full screen", "F11", checkable=True)

        self.options_menu = self._menu("&Options")
        self.chunk_size = self._action(self.options_menu, "Download &chunk size…")
        self.manage_users = self._action(self.options_menu, "&Manage users…")

        self.help_menu = self._menu("&Help")
        self.about = self._action(self.help_menu, "&About GEE-Assist")

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
