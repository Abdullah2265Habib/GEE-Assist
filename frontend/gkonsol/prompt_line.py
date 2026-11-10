"""The line the user types commands in.

Keys, as in other terminals:

* Enter      runs the line
* ↑ / ↓      go through the history (what was being typed comes back after the newest)
* Tab        completes the word at the cursor
* Ctrl+C     copies the selected text; without a selection, stops the running command
* Ctrl+L     clears the terminal
* Esc        empties the line
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QLineEdit, QWidget


class PromptLine(QLineEdit):
    submitted = pyqtSignal(str)
    interrupted = pyqtSignal()        # Ctrl+C with nothing selected
    clear_requested = pyqtSignal()    # Ctrl+L
    completion_requested = pyqtSignal()  # Tab

    def __init__(self, history: Callable[[], list[str]], parent: QWidget | None = None):
        """``history`` returns the commands typed so far, oldest first."""
        super().__init__(parent)
        self.setObjectName("GkonsolInput")
        self.setFrame(False)
        self._history = history
        self._browsing: Optional[int] = None  # index in the history while going through it
        self._draft = ""                      # what was typed before going through the history
        self.history_enabled = True           # off while answering a question

    def set_secret(self, secret: bool) -> None:
        self.setEchoMode(QLineEdit.EchoMode.Password if secret else QLineEdit.EchoMode.Normal)

    # ------------------------------------------------------------- keys
    def event(self, event: QEvent) -> bool:  # noqa: D102 - Tab must not move the focus away
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.completion_requested.emit()
            return True
        if event.type() == QEvent.Type.ShortcutOverride and self._is_terminal_key(event):
            event.accept()  # the terminal's own keys win over menu shortcuts
            return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt API)
        key, ctrl = event.key(), event.modifiers() & Qt.KeyboardModifier.ControlModifier
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            line = self.text()
            self.clear()
            self._browsing = None
            self.submitted.emit(line)
        elif key == Qt.Key.Key_Up and self.history_enabled:
            self._older()
        elif key == Qt.Key.Key_Down and self.history_enabled:
            self._newer()
        elif ctrl and key == Qt.Key.Key_C and not self.hasSelectedText():
            self.interrupted.emit()
        elif ctrl and key == Qt.Key.Key_L:
            self.clear_requested.emit()
        elif key == Qt.Key.Key_Escape:
            self.clear()
            self._browsing = None
        else:
            super().keyPressEvent(event)

    def _is_terminal_key(self, event: QKeyEvent) -> bool:
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        return bool(ctrl and event.key() in (Qt.Key.Key_C, Qt.Key.Key_L))

    # ------------------------------------------------------------- history
    def _older(self) -> None:
        entries = self._history()
        if not entries:
            return
        if self._browsing is None:
            self._draft, self._browsing = self.text(), len(entries)
        if self._browsing > 0:
            self._browsing -= 1
            self.setText(entries[self._browsing])

    def _newer(self) -> None:
        if self._browsing is None:
            return
        entries = self._history()
        if self._browsing < len(entries) - 1:
            self._browsing += 1
            self.setText(entries[self._browsing])
        else:
            self._browsing = None
            self.setText(self._draft)

    # ------------------------------------------------------------- completion
    def complete_with(self, start: int, candidates: list[str]) -> list[str]:
        """Complete the word from ``start`` to the cursor. Returns the candidates to list, if any.

        One candidate replaces the word (followed by a space); several extend it as far as
        they agree, and are listed when that adds nothing.
        """
        if not candidates:
            return []
        cursor = self.cursorPosition()
        typed = self.text()[start:cursor]
        if len(candidates) == 1:
            replacement = candidates[0] + " "
        else:
            replacement = _common_prefix(candidates)
            if len(replacement) <= len(typed):
                return candidates
        self.setText(self.text()[:start] + replacement + self.text()[cursor:])
        self.setCursorPosition(start + len(replacement))
        return []


def _common_prefix(words: list[str]) -> str:
    first, last = min(words), max(words)
    length = 0
    while length < min(len(first), len(last)) and first[length] == last[length]:
        length += 1
    return first[:length]
