"""The terminal's output area: styled lines, and a live region at the bottom redrawn in place.

It is what the commands' output (a ``Sink``) goes to on screen. New lines are added at
the end, or above the live region while one is shown, so a progress bar stays the last
thing in the terminal while messages appear above it.

The view follows new output while it is scrolled to the bottom; scrolled up, it stays
where the user put it. Only the last ``MAX_LINES`` lines are kept.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QTextCursor, QTextOption
from PyQt6.QtWidgets import QFrame, QPlainTextEdit, QWidget

from frontend.gkonsol import colors, text
from frontend.gkonsol.text import Line

MAX_LINES = 5000
MIN_COLUMNS = 20
DEFAULT_COLUMNS = 100  # until the view is first shown
FIT_SLACK = 4  # pixels: a view exactly as tall as its lines would still show a scroll bar


class TerminalView(QPlainTextEdit):
    clicked = pyqtSignal()  # a click that selected nothing: the input line takes the focus
    changed = pyqtSignal()  # lines were added, redrawn or removed

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("GkonsolOutput")
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # long lines wrap
        self.setMaximumBlockCount(MAX_LINES)  # the oldest lines go first; the live region is at the end
        self.setFont(colors.monospace_font())
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                     | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self._formats = colors.char_formats()
        self._empty = True          # no line written yet: the document's one block is unused
        self._live: list[Line] = []  # what the live region shows
        self._columns = DEFAULT_COLUMNS
        self._scroll_later = QTimer(self)  # owned by the view: it never fires after the view is gone
        self._scroll_later.setSingleShot(True)
        self._scroll_later.setInterval(0)
        self._scroll_later.timeout.connect(self._scroll_to_bottom)

    # ------------------------------------------------------------- Sink
    @property
    def columns(self) -> int:
        """Characters that fit on a line. While the view is hidden, as many as when it was last shown."""
        if self.isVisible():
            advance = max(1, self.fontMetrics().horizontalAdvance("M"))
            self._columns = max(MIN_COLUMNS, self.viewport().width() // advance - 1)
        return self._columns

    def write(self, lines: list[Line]) -> None:
        if not lines:
            return
        follow = self._at_bottom()
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        if self._live:
            cursor.setPosition(self._first_live_block().position())
            for spans in lines:  # each line goes above the live region
                self._insert(cursor, spans)
                cursor.insertBlock()
        else:
            cursor.movePosition(QTextCursor.MoveOperation.End)
            for spans in lines:
                self._new_line(cursor)
                self._insert(cursor, spans)
        cursor.endEditBlock()
        self._follow(follow)
        self.changed.emit()

    def set_live(self, lines: list[Line]) -> None:
        follow = self._at_bottom()
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        self._remove_live(cursor)
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for spans in lines:
            self._new_line(cursor)
            self._insert(cursor, spans)
        cursor.endEditBlock()
        self._live = [list(spans) for spans in lines]
        self._follow(follow)
        self.changed.emit()

    def end_live(self, keep: bool) -> None:
        if not keep:
            cursor = QTextCursor(self.document())
            self._remove_live(cursor)
        self._live = []
        self.changed.emit()

    def clear(self) -> None:  # noqa: D102 - keeps the live region, unlike QPlainTextEdit.clear
        live = self._live
        super().clear()
        self._empty, self._live = True, []
        if live:
            self.set_live(live)
        self.changed.emit()

    def plain_text(self) -> str:
        return self.toPlainText()

    def content_height(self, limit: int) -> int:
        """The pixels the lines need, padding included; counting stops past ``limit``."""
        total = float(self.height() - self.viewport().height())  # frame and padding
        if self._empty:
            return int(total)
        block = self.document().firstBlock()
        while block.isValid() and total <= limit:
            total += self.blockBoundingRect(block).height()
            block = block.next()
        return int(total + 0.999) + FIT_SLACK

    def scroll_to_bottom_later(self) -> None:
        self._scroll_later.start()

    # ------------------------------------------------------------- helpers
    def _insert(self, cursor: QTextCursor, spans: Line) -> None:
        for span in spans:
            if span.text:
                cursor.insertText(span.text, self._formats.get(span.style, self._formats[text.TEXT]))

    def _new_line(self, cursor: QTextCursor) -> None:
        if self._empty:
            self._empty = False
        else:
            cursor.insertBlock()

    def _first_live_block(self):
        document = self.document()
        return document.findBlockByNumber(document.blockCount() - len(self._live))

    def _remove_live(self, cursor: QTextCursor) -> None:
        if not self._live:
            return
        first = self._first_live_block()
        if first.blockNumber() == 0:  # the live region is all there is
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.removeSelectedText()
            self._empty = True
        else:  # from the end of the line before it, so no empty line is left behind
            previous = first.previous()
            cursor.setPosition(previous.position() + previous.length() - 1)
            cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
        self._live = []

    def _at_bottom(self) -> bool:
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - 2

    def _follow(self, follow: bool) -> None:
        if follow:
            self._scroll_to_bottom()
            self._scroll_later.start()  # again once the new lines are laid out

    def _scroll_to_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt API)
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and not self.textCursor().hasSelection():
            self.clicked.emit()
