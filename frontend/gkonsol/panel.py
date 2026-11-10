"""The terminal panel at the bottom of the signed-in window, like VS Code's.

``GkonsolPanel`` is the terminal: a header (its name and the Clear, Maximise and Close
buttons), the output, and the line commands are typed in, with the prompt before it.
While a command runs, the prompt shows what it is doing; while it asks a question,
the prompt is the question.

``TerminalArea`` puts a page above the terminal with a line between them that the
user drags to make the terminal taller or shorter. It shows, hides and maximises the
terminal, and remembers its height between sessions.
"""

from __future__ import annotations

import html
from typing import Any, Optional

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from frontend import theme
from frontend.gkonsol import colors, text
from frontend.gkonsol.command import Registry
from frontend.gkonsol.commands import build_registry
from frontend.gkonsol.commands.general import GKONSOL_VERSION
from frontend.gkonsol.history import GkonsolStore, History
from frontend.gkonsol.ports import AppPort, FormPort, PanelPort
from frontend.gkonsol.prompt_line import PromptLine
from frontend.gkonsol.scheduler import QtScheduler
from frontend.gkonsol.shell import Shell
from frontend.gkonsol.text import Line, Span
from frontend.gkonsol.view import TerminalView

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
SPINNER_MS = 90
BUTTON_SIZE = 26

TEXT_INDENT = 14          # the output's text and the prompt start this far from the edge


def stylesheet(font: QFont) -> str:
    """The panel's style. The font is named here: the app's style sheet would otherwise give the
    terminal its proportional font, and its columns would not line up."""
    family = f'font-family: "{font.family()}"; font-size: {font.pointSize()}pt;'
    return f"""
#GkonsolPanel {{ background: {colors.BACKGROUND}; border: none; }}
#GkonsolHeader {{ background: {colors.HEADER}; border: none; border-top: 1px solid {colors.BORDER};
                  border-bottom: 1px solid {colors.BORDER}; }}
QLabel#GkonsolTitle {{
    color: {theme.INK}; font-size: 8.5pt; font-weight: 600; letter-spacing: 1px;
    padding: 6px 2px 4px 2px; border-bottom: 2px solid {theme.LEAF};
}}
QToolButton#GkonsolButton {{ border: none; border-radius: 5px; background: transparent; }}
QToolButton#GkonsolButton:hover {{ background: {theme.MINT}; }}
QToolButton#GkonsolButton:pressed {{ background: {theme.BORDER}; }}
QPlainTextEdit#GkonsolOutput {{
    {family} background: {colors.BACKGROUND}; color: {theme.TEXT}; border: none;
    padding: 6px 4px 0 {TEXT_INDENT}px;
    selection-background-color: {colors.SELECTION}; selection-color: {theme.PRIMARY_TEXT};
}}
#GkonsolInputRow {{ background: {colors.BACKGROUND}; }}
QLabel#GkonsolPrompt {{ {family} background: transparent; padding: 0; }}
QLineEdit#GkonsolInput, QLineEdit#GkonsolInput:focus, QLineEdit#GkonsolInput:hover {{
    {family} background: transparent; border: none; padding: 0; margin: 0; color: {theme.INK};
    selection-background-color: {colors.SELECTION};
}}
"""


class PanelButton(QToolButton):
    """A small icon button in the terminal's header: clear, maximise, restore or close."""

    def __init__(self, kind: str, tip: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("GkonsolButton")
        self.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.kind = kind
        self.setToolTip(tip)

    def set_kind(self, kind: str, tip: str) -> None:
        self.kind = kind
        self.setToolTip(tip)
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        return QSize(BUTTON_SIZE, BUTTON_SIZE)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(theme.INK), 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        box = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        left, top, right, bottom, middle = box.left(), box.top(), box.right(), box.bottom(), box.center().x()
        if self.kind == "close":
            painter.drawLine(QPointF(left, top), QPointF(right, bottom))
            painter.drawLine(QPointF(right, top), QPointF(left, bottom))
        elif self.kind in ("maximize", "restore"):
            high, low = (top + 2, bottom - 2) if self.kind == "maximize" else (bottom - 2, top + 2)
            chevron = QPainterPath(QPointF(left, low))
            chevron.lineTo(middle, high)
            chevron.lineTo(right, low)
            painter.drawPath(chevron)
        elif self.kind == "clear":  # a waste bin
            painter.drawLine(QPointF(left - 1, top + 2), QPointF(right + 1, top + 2))
            painter.drawLine(QPointF(middle - 2, top), QPointF(middle + 2, top))
            painter.drawRoundedRect(QRectF(left + 1, top + 4, box.width() - 2, box.height() - 4), 1.5, 1.5)
            for x in (middle - 1.6, middle + 1.6):
                painter.drawLine(QPointF(x, top + 6.5), QPointF(x, bottom - 2))
        painter.end()


def spans_html(spans: Line) -> str:
    """Spans as rich text for a label, in the terminal's colours."""
    parts = []
    for span in spans:
        colour, bold = colors.STYLE_COLOURS.get(span.style, colors.STYLE_COLOURS[text.TEXT])
        weight = "font-weight:600;" if bold else ""
        parts.append(f'<span style="color:{colour};{weight}">{html.escape(span.text).replace(" ", "&nbsp;")}</span>')
    return "".join(parts)


class GkonsolPanel(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("GkonsolPanel")
        font = colors.monospace_font()
        self.setStyleSheet(stylesheet(font))
        self.shell: Optional[Shell] = None
        self._panel: Optional[PanelPort] = None
        self._frame = 0

        # ---- header
        self.title = QLabel("GKONSOL", objectName="GkonsolTitle")
        self.title.setToolTip("gkonsol, the GEE-Assist command line. Type help to see its commands.")
        self.clear_button = PanelButton("clear", "Clear the terminal (Ctrl+L)")
        self.maximize_button = PanelButton("maximize", "Maximise the terminal")
        self.close_button = PanelButton("close", "Hide the terminal (Ctrl+`)")
        header = QFrame(objectName="GkonsolHeader")
        row = QHBoxLayout(header)
        row.setContentsMargins(14, 0, 8, 0)
        row.setSpacing(2)
        row.addWidget(self.title, 0, Qt.AlignmentFlag.AlignBottom)
        row.addStretch(1)
        for button in (self.clear_button, self.maximize_button, self.close_button):
            row.addWidget(button)

        # ---- output and input
        self.view = TerminalView()
        self.view.document().setDocumentMargin(0)  # the text starts where the prompt does
        self.prompt = QLabel(objectName="GkonsolPrompt")
        self.prompt.setFont(font)
        self.prompt.setTextFormat(Qt.TextFormat.RichText)
        self.input = PromptLine(self._history_entries)
        self.input.setFont(font)
        input_row = QWidget(objectName="GkonsolInputRow")
        input_row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        line = QHBoxLayout(input_row)
        line.setContentsMargins(TEXT_INDENT, 0, 12, 8)
        line.setSpacing(0)
        line.addWidget(self.prompt)
        line.addWidget(self.input, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self.view, 1)
        layout.addWidget(input_row)

        self._spinner = QTimer(self)
        self._spinner.setInterval(SPINNER_MS)
        self._spinner.timeout.connect(self._spin)
        self.view.clicked.connect(self.focus_input)
        self.setFocusProxy(self.input)

    # ------------------------------------------------------------- starting
    def start(self, facade: Any, app: AppPort, form: FormPort, panel: PanelPort, history: History,
              registry: Optional[Registry] = None) -> Shell:
        """Create the shell that runs the commands typed here."""
        self._panel = panel
        self.shell = Shell(registry or build_registry(), facade, app, form, panel, self.view, QtScheduler(self), history)
        self.shell.on_state = self.refresh_prompt
        self.input.submitted.connect(self._submit)
        self.input.interrupted.connect(self._interrupt)
        self.input.clear_requested.connect(self.shell.clear)
        self.input.completion_requested.connect(self._complete)
        self.clear_button.clicked.connect(self.shell.clear)
        self.maximize_button.clicked.connect(lambda: panel.set_terminal_maximized(not panel.is_terminal_maximized()))
        self.close_button.clicked.connect(panel.hide_terminal)
        self.shell.out.print(Span(f"gkonsol {GKONSOL_VERSION}", text.ACCENT),
                             Span(" — the GEE-Assist command line. Type ", text.MUTED), Span("help", text.INFO),
                             Span(" to see the commands, or ", text.MUTED), Span("help <command>", text.INFO),
                             Span(" for one.", text.MUTED))
        self.refresh_prompt()
        return self.shell

    def shutdown(self) -> None:
        """The window is closing: end the running command (a browser sign-in stops waiting)."""
        if self.shell is not None:
            self.shell.stop()
        self._spinner.stop()

    def focus_input(self) -> None:
        self.input.setFocus()

    def show_maximized_state(self, maximized: bool) -> None:
        if maximized:
            self.maximize_button.set_kind("restore", "Restore the terminal's size")
        else:
            self.maximize_button.set_kind("maximize", "Maximise the terminal")

    # ------------------------------------------------------------- the prompt
    def refresh_prompt(self) -> None:
        """Show the prompt, the question being asked, or what the running command does."""
        if self.shell is None:
            return
        question = self.shell.runner.asking
        if question is not None:
            self._spinner.stop()
            self.input.set_secret(question.secret)
            self.input.history_enabled = False
            self.prompt.setText(spans_html([Span(question.prompt + " ", text.BOLD)]))
        elif self.shell.running is not None:
            self.input.set_secret(False)
            self.input.history_enabled = False
            if not self._spinner.isActive():
                self._spinner.start()
            self._spin()
        else:
            self._spinner.stop()
            self.input.set_secret(False)
            self.input.history_enabled = True
            self.prompt.setText(spans_html(self.shell.prompt()))

    def _spin(self) -> None:
        if self.shell is None or self.shell.running is None or self.shell.runner.asking is not None:
            return
        self._frame = (self._frame + 1) % len(SPINNER)
        self.prompt.setText(spans_html([Span(f"{SPINNER[self._frame]} ", text.ACCENT),
                                        Span(self.shell.status() + "  ", text.MUTED)]))

    # ------------------------------------------------------------- input
    def _history_entries(self) -> list[str]:
        return self.shell.history.entries if self.shell is not None else []

    def _submit(self, line: str) -> None:
        self.shell.submit(line)
        self.refresh_prompt()

    def _interrupt(self) -> None:
        if self.shell.running is not None:
            self.shell.interrupt()
        else:  # like other shells: the line typed so far is dropped
            self.shell.out.lines([self.shell.prompt() + [Span(self.input.text(), text.COMMAND), Span("^C", text.MUTED)]])
            self.input.clear()
        self.refresh_prompt()

    def _complete(self) -> None:
        before = self.input.text()[:self.input.cursorPosition()]
        start, candidates = self.shell.complete(before)
        listed = self.input.complete_with(start, candidates)
        if listed:
            self.shell.out.lines([[Span(row, text.MUTED)] for row in text.columns(listed, self.view.columns)])


class TerminalArea(QSplitter):
    """A page above, the terminal below, and a line between them to drag. The terminal starts hidden.

    Dragging the line to the top hides the page: the terminal is then maximised, as with
    the Maximise button. The terminal's height is saved a moment after it was last changed.
    """

    visibility_changed = pyqtSignal(bool)
    DEFAULT_HEIGHT = 300
    MIN_HEIGHT = 110        # the header, a line of output and the prompt
    MIN_PAGE = 120          # the page keeps at least this much unless the terminal is maximised
    SAVE_DELAY_MS = 600

    def __init__(self, page: QWidget, terminal: GkonsolPanel, store: Optional[GkonsolStore] = None,
                 parent: QWidget | None = None):
        super().__init__(Qt.Orientation.Vertical, parent)
        self.setObjectName("TerminalArea")
        self.setHandleWidth(4)
        self.setStyleSheet(f"""
            QSplitter#TerminalArea::handle {{ background: {colors.BORDER}; }}
            QSplitter#TerminalArea::handle:hover, QSplitter#TerminalArea::handle:pressed {{ background: {theme.OCEAN}; }}
        """)
        self.page, self.terminal, self._store = page, terminal, store
        self.addWidget(page)
        self.addWidget(terminal)
        self.setCollapsible(0, True)    # maximised, the page gives all its room to the terminal
        self.setCollapsible(1, False)
        self.setStretchFactor(0, 1)
        self.setStretchFactor(1, 0)
        terminal.setMinimumHeight(self.MIN_HEIGHT)
        saved = store.load().get("panel_height") if store else None
        self._height = saved if isinstance(saved, int) and saved >= self.MIN_HEIGHT else self.DEFAULT_HEIGHT
        self._maximized = False
        self._save_later = QTimer(self)
        self._save_later.setSingleShot(True)
        self._save_later.setInterval(self.SAVE_DELAY_MS)
        self._save_later.timeout.connect(self._save)
        terminal.hide()
        self.splitterMoved.connect(self._dragged)

    # ------------------------------------------------------------- showing
    def is_terminal_visible(self) -> bool:
        return not self.terminal.isHidden()

    def toggle_terminal(self) -> None:
        if self.is_terminal_visible():
            self.hide_terminal()
        else:
            self.show_terminal()

    def show_terminal(self) -> None:
        if not self.is_terminal_visible():
            self.terminal.show()
            self._apply()
            self.visibility_changed.emit(True)
        self.terminal.focus_input()

    def hide_terminal(self) -> None:
        if not self.is_terminal_visible():
            return
        self._set_maximized(False)
        self.terminal.hide()
        self._save()
        self.visibility_changed.emit(False)
        self.page.setFocus()

    # ------------------------------------------------------------- PanelPort
    def is_terminal_maximized(self) -> bool:
        return self._maximized

    def set_terminal_maximized(self, on: bool) -> None:
        if not self.is_terminal_visible():
            self.show_terminal()
        self._set_maximized(on)
        self._apply()

    def terminal_height(self) -> int:
        return self.sizes()[1] if self.is_terminal_visible() and not self._maximized else self._height

    def set_terminal_height(self, pixels: int) -> None:
        self._height = max(self.MIN_HEIGHT, pixels)
        self._set_maximized(False)
        self._save()
        if self.is_terminal_visible():
            self._apply()

    # ------------------------------------------------------------- helpers
    def _set_maximized(self, on: bool) -> None:
        if on != self._maximized:
            self._maximized = on
            self.terminal.show_maximized_state(on)

    def _apply(self) -> None:
        total = max(1, self.height() - self.handleWidth())
        if self._maximized:
            self.setSizes([0, total])
        else:
            height = max(self.MIN_HEIGHT, min(self._height, total - self.MIN_PAGE))
            self.setSizes([max(0, total - height), height])

    def _dragged(self, position: int, index: int) -> None:
        page, terminal = self.sizes()
        self._set_maximized(page == 0)  # dragged to the top: maximised; dragged down again: not
        if page > 0:
            self._height = terminal
            self._save_later.start()

    def _save(self) -> None:
        self._save_later.stop()
        if self._store is not None:
            self._store.update(panel_height=self._height)
