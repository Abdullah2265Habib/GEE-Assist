"""The side bar's drawn icons and their animations (no window on screen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtCore import QRectF, Qt  # noqa: E402
from PyQt6.QtGui import QImage, QPainter  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from frontend.widgets.side_icons import DownloadIcon, TerminalIcon, WritingIcon  # noqa: E402

RECT = QRectF(0, 0, 44, 44)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _render(icon, t):
    image = QImage(44, 44, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    icon.paint(painter, RECT, t)
    painter.end()
    return image


def test_icons_draw_something_at_rest_and_while_animated(app):
    for icon in (DownloadIcon(), WritingIcon(), TerminalIcon()):
        for t in (None, 0.0, 0.3, 0.8):
            image = _render(icon, t)
            assert any(image.pixelColor(x, y).alpha() for x in range(44) for y in range(44))


def test_download_arrow_slides_down_then_wraps_to_the_top(app):
    tips = [DownloadIcon.arrow_tip(RECT, t) for t in (0.0, 0.25, 0.5, 0.75)]
    assert tips == sorted(tips) and tips[0] < tips[-1]                 # moving down
    assert DownloadIcon.arrow_tip(RECT, None) == DownloadIcon.arrow_tip(RECT, 0.0)  # at rest: in place
    assert _render(DownloadIcon(), 0.0) != _render(DownloadIcon(), 0.5)


def test_pencil_writes_the_lines_one_after_another(app):
    progress = WritingIcon.line_progress
    assert [progress(None, line) for line in range(3)] == [1, 1, 1]   # at rest: all written
    assert [progress(0.0, line) for line in range(3)] == [0, 0, 0]    # a loop starts on a blank sheet
    assert [progress(0.5, line) for line in range(3)] == [1, 0.5, 0]  # half-way: on the second line
    assert _render(WritingIcon(), 0.2) != _render(WritingIcon(), 0.6)


def test_terminal_types_after_the_prompt_while_the_cursor_blinks(app):
    assert TerminalIcon.typed(None) == 0 and TerminalIcon.cursor_visible(None)   # at rest: a bare prompt
    assert [TerminalIcon.typed(t) for t in (0.0, 0.3, 0.55, 0.8, 0.99)] == [0, 1, 2, 3, 3]
    blinks = [TerminalIcon.cursor_visible(t / 16) for t in range(16)]
    assert True in blinks and False in blinks
    assert _render(TerminalIcon(), 0.0) != _render(TerminalIcon(), 0.8)
