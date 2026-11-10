"""The terminal panel and the area that puts it under the page (no window on screen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QLineEdit  # noqa: E402

from frontend.gkonsol.history import GkonsolStore, History  # noqa: E402
from frontend.gkonsol.panel import GkonsolPanel, TerminalArea  # noqa: E402
from frontend.gkonsol.ports import MemoryForm  # noqa: E402
from tests.gkonsol_fakes import FakeApp, FakePanel, facade  # noqa: E402

CTRL = Qt.KeyboardModifier.ControlModifier


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(app):
    widget = GkonsolPanel()
    fake = facade()
    port = FakePanel()
    widget.start(fake, FakeApp(), MemoryForm(fake), port, History())
    widget.port, widget.fake = port, fake
    widget.resize(700, 300)
    widget.show()
    yield widget
    widget.shutdown()
    widget.deleteLater()


def _type(panel, line):
    panel.input.setText(line)
    QTest.keyClick(panel.input, Qt.Key.Key_Return)


def _plain(rich: str) -> str:
    from PyQt6.QtGui import QTextDocument

    document = QTextDocument()
    document.setHtml(rich)
    return document.toPlainText().replace("\xa0", " ")


# ------------------------------------------------------------------ the panel
def test_the_panel_greets_and_shows_the_prompt(panel):
    assert "gkonsol 1.0 — the GEE-Assist command line. Type help" in panel.view.toPlainText()
    assert _plain(panel.prompt.text()) == "ayesha@gkonsol ~ $ "
    assert panel.title.text() == "GKONSOL"


def test_typed_commands_run(panel):
    _type(panel, "echo Hello from gkonsol")
    assert panel.view.toPlainText().endswith("ayesha@gkonsol ~ $ echo Hello from gkonsol\nHello from gkonsol")


def test_a_question_replaces_the_prompt(panel):
    _type(panel, "signout")
    assert _plain(panel.prompt.text()) == "Sign out of GEE-Assist? [y/N] "
    assert not panel.input.history_enabled
    _type(panel, "n")
    assert _plain(panel.prompt.text()) == "ayesha@gkonsol ~ $ " and panel.input.history_enabled


def test_a_running_command_shows_a_spinner_and_ctrl_c_stops_it(panel):
    panel.fake.list_downloads.return_value = []
    _type(panel, "download speed")
    assert "download speed is running  (Ctrl+C to stop)" in _plain(panel.prompt.text())
    assert panel._spinner.isActive()
    QTest.keyClick(panel.input, Qt.Key.Key_C, CTRL)
    assert panel.shell.running is None and not panel._spinner.isActive()
    assert _plain(panel.prompt.text()) == "ayesha@gkonsol ~ $ "


def test_ctrl_c_drops_the_typed_line(panel):
    panel.input.setText("download sta")
    QTest.keyClick(panel.input, Qt.Key.Key_C, CTRL)
    assert panel.view.toPlainText().endswith("ayesha@gkonsol ~ $ download sta^C") and panel.input.text() == ""


def test_tab_completes_and_lists(panel):
    panel.input.setText("hist")
    QTest.keyClick(panel.input, Qt.Key.Key_Tab)
    assert panel.input.text() == "history "
    panel.input.setText("download s")
    QTest.keyClick(panel.input, Qt.Key.Key_Tab)
    assert panel.input.text() == "download s"
    assert panel.view.toPlainText().split("\n")[-1].split() == ["start", "show", "speed"]


def test_ctrl_l_and_the_clear_button_clear_the_output(panel):
    _type(panel, "echo one")
    QTest.keyClick(panel.input, Qt.Key.Key_L, CTRL)
    assert panel.view.toPlainText() == ""
    _type(panel, "echo two")
    panel.clear_button.click()
    assert panel.view.toPlainText() == ""


def test_header_buttons_maximise_and_hide(panel):
    panel.maximize_button.click()
    assert panel.port.maximized
    panel.close_button.click()
    assert panel.port.closed


def test_the_prompt_follows_short_output_and_sits_at_the_bottom_of_long_output(panel):
    QApplication.processEvents()
    panel.fit_output()
    QApplication.processEvents()  # the layout follows the new height
    short = panel._input_row.geometry().top()
    assert panel.view.maximumHeight() < panel.height() and short < panel.height() // 2
    for n in range(80):
        panel.shell.out.print(f"line {n}")
    QApplication.processEvents()
    panel.fit_output()
    QApplication.processEvents()
    assert panel.view.maximumHeight() > panel.height()  # no longer capped: the output scrolls
    assert panel._input_row.geometry().bottom() >= panel.height() - 2


def test_the_input_is_a_plain_line(panel):
    assert isinstance(panel.input, QLineEdit) and panel.input.font().fixedPitch()


# ------------------------------------------------------------------ the area under the page
@pytest.fixture
def area(app, tmp_path):
    page = QLabel("page")
    terminal = GkonsolPanel()
    store = GkonsolStore(tmp_path / "gkonsol.json")
    widget = TerminalArea(page, terminal, store)
    fake = facade()
    terminal.start(fake, FakeApp(), MemoryForm(fake), widget, History())
    widget.resize(800, 700)
    widget.show()
    QApplication.processEvents()
    widget.store = store
    yield widget
    terminal.shutdown()
    widget.deleteLater()


def test_the_terminal_starts_hidden_and_opens_below_the_page(area):
    assert not area.is_terminal_visible() and area.widget(0) is area.page and area.widget(1) is area.terminal
    shown = []
    area.visibility_changed.connect(shown.append)
    area.toggle_terminal()
    assert area.is_terminal_visible() and shown == [True]
    assert area.sizes()[1] == TerminalArea.DEFAULT_HEIGHT and area.sizes()[0] > 0
    area.toggle_terminal()
    assert not area.is_terminal_visible() and shown == [True, False]


def test_maximise_and_restore(area):
    area.show_terminal()
    area.set_terminal_maximized(True)
    assert area.is_terminal_maximized() and area.sizes()[0] == 0
    assert area.terminal.maximize_button.kind == "restore"
    area.set_terminal_maximized(False)
    assert area.sizes()[1] == TerminalArea.DEFAULT_HEIGHT and area.terminal.maximize_button.kind == "maximize"


def test_maximising_a_hidden_terminal_shows_it(area):
    area.set_terminal_maximized(True)
    assert area.is_terminal_visible() and area.sizes()[0] == 0


def test_height_can_be_set_and_is_saved(area):
    area.show_terminal()
    area.set_terminal_height(420)
    assert area.terminal_height() == 420 and area.store.load()["panel_height"] == 420
    area.set_terminal_height(5000)  # more than fits: the page keeps a little
    assert area.sizes()[0] >= TerminalArea.MIN_PAGE - 1


def test_dragging_resizes_and_dragging_to_the_top_maximises(area):
    area.show_terminal()
    area.moveSplitter(300, 1)
    assert not area.is_terminal_maximized() and area.terminal_height() == area.sizes()[1] > TerminalArea.DEFAULT_HEIGHT
    area.moveSplitter(0, 1)
    assert area.is_terminal_maximized()
    area.moveSplitter(400, 1)
    assert not area.is_terminal_maximized()


def test_the_height_comes_back_next_time(area, tmp_path):
    area.show_terminal()
    area.set_terminal_height(360)
    again = TerminalArea(QLabel("page"), GkonsolPanel(), area.store)
    assert again.terminal_height() == 360
    again.deleteLater()


def test_commands_resize_the_terminal(area):
    area.show_terminal()
    area.terminal.shell.submit("panel height 250")
    assert area.terminal_height() == 250
    area.terminal.shell.submit("panel max")
    assert area.is_terminal_maximized()
    area.terminal.shell.submit("exit")
    assert not area.is_terminal_visible()
