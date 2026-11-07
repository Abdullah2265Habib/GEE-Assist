"""The menu bar along the top of the signed-in window (no window on screen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication  # noqa: E402

from frontend.widgets.menu_bar import AppMenuBar  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def bar(app):
    menu_bar = AppMenuBar()
    yield menu_bar
    menu_bar.deleteLater()


def _items(menu):
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def test_has_the_classic_menus_in_order(bar):
    assert [action.text() for action in bar.actions()] == ["&File", "&Edit", "&View", "&Options", "&Help"]


def test_menus_hold_the_expected_items(bar):
    assert _items(bar.file_menu) == ["&New request", "Sign &out", "E&xit"]
    assert _items(bar.edit_menu) == ["&Undo", "&Redo", "Cu&t", "&Copy", "&Paste", "Select &all"]
    assert _items(bar.view_menu) == ["&Dashboard", "&Query Input", "Do&wnloads", "&Account", "&Side bar",
                                     "&Full screen"]
    assert _items(bar.options_menu) == ["Download &chunk size…", "&Manage users…"]
    assert _items(bar.help_menu) == ["&About GEE-Assist"]


def test_shortcuts_are_the_familiar_ones(bar):
    shortcuts = {action.text(): action.shortcut().toString() for menu in
                 (bar.file_menu, bar.edit_menu, bar.view_menu) for action in menu.actions()}
    assert shortcuts["&New request"] == "Ctrl+N" and shortcuts["E&xit"] == "Ctrl+Q"
    assert shortcuts["&Undo"] == "Ctrl+Z" and shortcuts["&Redo"] == "Ctrl+Y"
    assert shortcuts["Cu&t"] == "Ctrl+X" and shortcuts["&Copy"] == "Ctrl+C" and shortcuts["&Paste"] == "Ctrl+V"
    assert shortcuts["&Dashboard"] == "Ctrl+1" and shortcuts["&Full screen"] == "F11"


def test_side_bar_and_full_screen_are_on_off_items(bar):
    assert bar.toggle_side_bar.isCheckable() and bar.full_screen.isCheckable()
    assert not bar.view_dashboard.isCheckable()
