"""The line commands are typed in: Enter, history, Tab completion, Ctrl+C and Ctrl+L (no window on screen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from frontend.gkonsol.prompt_line import PromptLine  # noqa: E402

CTRL = Qt.KeyboardModifier.ControlModifier


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def history():
    return ["gee verify", "form show", "download watch"]


@pytest.fixture
def line(app, history):
    widget = PromptLine(lambda: history)
    events = []
    widget.submitted.connect(lambda text: events.append(("submitted", text)))
    widget.interrupted.connect(lambda: events.append(("interrupted",)))
    widget.clear_requested.connect(lambda: events.append(("clear",)))
    widget.completion_requested.connect(lambda: events.append(("complete",)))
    widget.events = events
    yield widget
    widget.deleteLater()


def test_enter_submits_and_empties_the_line(line):
    QTest.keyClicks(line, "whoami")
    QTest.keyClick(line, Qt.Key.Key_Return)
    assert line.events == [("submitted", "whoami")] and line.text() == ""


def test_up_and_down_go_through_the_history(line):
    QTest.keyClicks(line, "dat")
    QTest.keyClick(line, Qt.Key.Key_Up)
    assert line.text() == "download watch"
    QTest.keyClick(line, Qt.Key.Key_Up)
    QTest.keyClick(line, Qt.Key.Key_Up)
    QTest.keyClick(line, Qt.Key.Key_Up)  # the oldest stays
    assert line.text() == "gee verify"
    QTest.keyClick(line, Qt.Key.Key_Down)
    assert line.text() == "form show"
    QTest.keyClick(line, Qt.Key.Key_Down)
    QTest.keyClick(line, Qt.Key.Key_Down)  # past the newest: what was being typed
    assert line.text() == "dat"


def test_history_can_be_turned_off(line):
    line.history_enabled = False
    QTest.keyClick(line, Qt.Key.Key_Up)
    assert line.text() == ""


def test_tab_asks_for_completion_and_keeps_the_focus(line):
    line.show()
    line.setFocus()
    QTest.keyClick(line, Qt.Key.Key_Tab)
    assert line.events == [("complete",)]


def test_ctrl_c_interrupts_without_a_selection_and_copies_with_one(line):
    QTest.keyClick(line, Qt.Key.Key_C, CTRL)
    assert line.events == [("interrupted",)]
    line.setText("gee verify")
    line.selectAll()
    QTest.keyClick(line, Qt.Key.Key_C, CTRL)
    assert line.events == [("interrupted",)] and QApplication.clipboard().text() == "gee verify"


def test_ctrl_l_clears_and_escape_empties_the_line(line):
    QTest.keyClick(line, Qt.Key.Key_L, CTRL)
    QTest.keyClicks(line, "something")
    QTest.keyClick(line, Qt.Key.Key_Escape)
    assert line.events == [("clear",)] and line.text() == ""


def test_secret_answers_are_hidden(line):
    line.set_secret(True)
    assert line.echoMode() == line.EchoMode.Password
    line.set_secret(False)
    assert line.echoMode() == line.EchoMode.Normal


@pytest.mark.parametrize("typed, start, candidates, result, listed", [
    ("downl", 0, ["download"], "download ", []),
    ("download wa", 9, ["watch"], "download watch ", []),
    ("form set bands B", 15, ["B1", "B11", "B12"], "form set bands B1", []),
    ("form set bands B1", 15, ["B1", "B11", "B12"], "form set bands B1", ["B1", "B11", "B12"]),
    ("gee x", 4, [], "gee x", []),
])
def test_completion(line, typed, start, candidates, result, listed):
    line.setText(typed)
    assert line.complete_with(start, candidates) == listed
    assert line.text() == result and line.cursorPosition() == len(result)


def test_completion_in_the_middle_of_the_line(line):
    line.setText("download wa 3f9a")
    line.setCursorPosition(len("download wa"))
    line.complete_with(9, ["watch"])
    assert line.text() == "download watch  3f9a" and line.cursorPosition() == len("download watch ")
