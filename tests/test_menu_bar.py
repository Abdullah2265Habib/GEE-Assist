"""The menu bar along the top of the signed-in window (no window on screen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QLineEdit, QPushButton, QVBoxLayout, QWidget  # noqa: E402

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
    assert [action.text() for action in bar.actions()] == ["&File", "&Edit", "&View", "&Terminal", "&Options", "&Help"]


def test_menus_hold_the_expected_items(bar):
    assert _items(bar.file_menu) == ["&New request", "Sign &out", "E&xit"]
    assert _items(bar.edit_menu) == ["&Undo", "&Redo", "Cu&t", "&Copy", "&Paste", "Select &all"]
    assert _items(bar.view_menu) == ["&Dashboard", "&Query Input", "Do&wnloads", "&Account", "&Side bar",
                                     "&Terminal", "&Full screen", "&Theme"]
    assert _items(bar.terminal_menu)[:4] == ["&Show terminal	Ctrl+`", "&Maximise terminal", "&Clear terminal",
                                             "S&top running command"]
    assert _items(bar.options_menu) == ["Download &chunk size…", "&Manage users…"]
    assert _items(bar.help_menu) == ["&About GEE-Assist"]


def test_shortcuts_are_the_familiar_ones(bar):
    shortcuts = {action.text(): action.shortcut().toString() for menu in
                 (bar.file_menu, bar.edit_menu, bar.view_menu) for action in menu.actions()}
    assert shortcuts["&New request"] == "Ctrl+N" and shortcuts["E&xit"] == "Ctrl+Q"
    assert shortcuts["&Undo"] == "Ctrl+Z" and shortcuts["&Redo"] == "Ctrl+Y"
    assert shortcuts["Cu&t"] == "Ctrl+X" and shortcuts["&Copy"] == "Ctrl+C" and shortcuts["&Paste"] == "Ctrl+V"
    assert shortcuts["&Dashboard"] == "Ctrl+1" and shortcuts["&Full screen"] == "F11"
    assert shortcuts["&Terminal"] == "Ctrl+`"  # as in VS Code


def test_the_terminal_menu_shows_the_terminal_shortcut_without_taking_it(bar):
    assert bar.show_terminal.shortcut().isEmpty()  # Ctrl+` is View → Terminal's: one action per shortcut
    assert bar.show_terminal.text().endswith("	Ctrl+`")
    assert bar.show_terminal.isCheckable() and bar.maximize_terminal.isCheckable()
    assert bar.terminal_menu.toolTipsVisible()


def test_side_bar_and_full_screen_are_on_off_items(bar):
    assert bar.toggle_side_bar.isCheckable() and bar.full_screen.isCheckable() and bar.toggle_terminal.isCheckable()
    assert not bar.view_dashboard.isCheckable()


@pytest.fixture
def form(app):
    """A window with a text field and a button, the field holding the cursor."""
    window = QWidget()
    field, button = QLineEdit("Faisalabad AOI"), QPushButton("Go")
    layout = QVBoxLayout(window)
    layout.addWidget(field)
    layout.addWidget(button)
    window.show()
    window.activateWindow()
    field.setFocus()
    QApplication.processEvents()
    if QApplication.focusWidget() is not field:
        pytest.skip("this platform does not give the test window keyboard focus")
    yield field, button
    window.close()
    window.deleteLater()


def test_edit_commands_act_on_the_field_with_the_cursor(bar, form):
    field, _ = form
    bar.select_all.trigger()
    assert field.selectedText() == "Faisalabad AOI"
    bar.copy.trigger()
    assert QApplication.clipboard().text() == "Faisalabad AOI"
    bar.cut.trigger()
    assert field.text() == ""
    bar.undo.trigger()
    assert field.text() == "Faisalabad AOI"
    field.setCursorPosition(len(field.text()))
    bar.paste.trigger()
    assert field.text() == "Faisalabad AOIFaisalabad AOI"


def test_edit_items_are_greyed_out_when_they_cannot_apply(bar, form):
    field, button = form
    field.deselect()
    bar._update_edit_items()  # as when the Edit menu opens
    assert not bar.copy.isEnabled() and not bar.cut.isEnabled() and bar.select_all.isEnabled()

    button.setFocus()
    QApplication.processEvents()
    bar._update_edit_items()  # no text field has the cursor
    assert not any(action.isEnabled() for action in (bar.undo, bar.copy, bar.paste, bar.select_all))

    bar._enable_edit_items()  # as when the menu closes
    assert bar.copy.isEnabled()


def test_view_menu_has_a_theme_switcher_set_to_light(bar):
    assert _items(bar.theme_menu) == ["Light", "Dark – blue-green", "Dark – grey"]
    assert [a.isChecked() for a in bar.theme_menu.actions()] == [True, False, False]  # light by default


def test_choosing_another_theme_asks_for_it(bar):
    chosen = []
    bar.theme_chosen.connect(chosen.append)
    bar.theme_actions["light"].trigger()        # already in use: nothing to do
    bar.theme_actions["dark-grey"].trigger()
    assert chosen == ["dark-grey"]

    bar.show_current_theme()                    # e.g. switching was cancelled
    assert bar.theme_actions["light"].isChecked() and not bar.theme_actions["dark-grey"].isChecked()
