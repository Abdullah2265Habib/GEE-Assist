"""The terminal's output area: styled lines, a live region redrawn in place, scrolling (no window on screen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtGui import QTextCursor  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from frontend import palette  # noqa: E402
from frontend.gkonsol import text  # noqa: E402
from frontend.gkonsol.output import Writer  # noqa: E402
from frontend.gkonsol.text import Span  # noqa: E402
from frontend.gkonsol.view import TerminalView  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(app):
    widget = TerminalView()
    widget.resize(600, 200)
    yield widget
    widget.deleteLater()


def _lines(view):
    return view.toPlainText().split("\n") if view.toPlainText() else []


def test_lines_are_added_at_the_end(view):
    view.write([text.line("one"), text.line("two")])
    view.write([[]])
    assert _lines(view) == ["one", "two", ""]


def test_spans_keep_their_colours(view):
    view.write([[Span("✗ ", text.ERROR), Span("failed", text.ERROR), Span(" ok", text.SUCCESS)]])
    cursor = QTextCursor(view.document())
    cursor.setPosition(3)
    assert cursor.charFormat().foreground().color().name().upper() == palette.ACTIVE["ERROR"].upper()
    cursor.setPosition(len("✗ failed o"))
    assert cursor.charFormat().foreground().color().name().upper() == palette.ACTIVE["SUCCESS"].upper()


def test_the_live_region_is_redrawn_in_place(view):
    view.write([text.line("Starting")])
    view.set_live([text.line("10%"), text.line("speed 1 MB/s")])
    view.set_live([text.line("55%"), text.line("speed 4 MB/s")])
    assert _lines(view) == ["Starting", "55%", "speed 4 MB/s"]


def test_output_goes_above_the_live_region(view):
    view.set_live([text.line("42%")])
    view.write([text.line("Chunk 1 merged"), text.line("Chunk 2 merged")])
    view.set_live([text.line("60%")])
    assert _lines(view) == ["Chunk 1 merged", "Chunk 2 merged", "60%"]


def test_a_live_region_can_shrink_and_grow(view):
    view.write([text.line("top")])
    view.set_live([text.line("a"), text.line("b"), text.line("c")])
    view.set_live([text.line("x")])
    assert _lines(view) == ["top", "x"]
    view.set_live([text.line("1"), text.line("2")])
    assert _lines(view) == ["top", "1", "2"]


def test_ending_the_live_region_keeps_or_removes_it(view):
    view.write([text.line("top")])
    view.set_live([text.line("100%")])
    view.end_live(keep=True)
    view.write([text.line("after")])
    assert _lines(view) == ["top", "100%", "after"]
    view.set_live([text.line("spinner")])
    view.end_live(keep=False)
    assert _lines(view) == ["top", "100%", "after"]


def test_clear_keeps_the_live_region(view):
    view.write([text.line("old")])
    view.set_live([text.line("42%")])
    view.clear()
    assert _lines(view) == ["42%"]
    view.write([text.line("new")])
    assert _lines(view) == ["new", "42%"]


def test_only_the_last_lines_are_kept(view, monkeypatch):
    view.setMaximumBlockCount(10)
    view.write([text.line(f"line {n}") for n in range(30)])
    view.set_live([text.line("live")])
    view.write([text.line("one more")])
    lines = _lines(view)
    assert len(lines) == 10 and lines[-2:] == ["one more", "live"]


def test_new_output_is_followed_at_the_bottom(view):
    view.show()
    view.write([text.line(f"line {n}") for n in range(200)])
    QApplication.processEvents()
    bar = view.verticalScrollBar()
    assert bar.maximum() > 0 and bar.value() == bar.maximum()
    bar.setValue(0)  # the user scrolls up to read
    view.write([text.line("more")])
    QApplication.processEvents()
    assert bar.value() == 0


def test_columns_follow_the_width(view):
    view.show()  # the viewport is laid out once the view is shown
    view.resize(300, 200)
    QApplication.processEvents()
    narrow = view.columns
    view.resize(900, 200)
    QApplication.processEvents()
    assert view.columns > narrow >= 20


def test_a_hidden_view_keeps_the_width_it_was_last_shown_at(view):
    assert view.columns == 100  # never shown yet
    view.show()
    view.resize(400, 200)
    QApplication.processEvents()
    shown = view.columns
    view.hide()
    view.resize(150, 200)
    assert view.columns == shown != 100


def test_a_writer_can_print_into_the_view(view):
    out = Writer(view)
    out.success("Signed in")
    out.table(["A", "B"], [["1", "2"]])
    assert _lines(view) == ["✓ Signed in", "A  B", "1  2"]
