"""Floating "describe your request" button for the parameter form (UC-02).

A round button sits in the bottom-right corner of the form. Clicking it (or
Ctrl+K) opens a card above it where the user types a request in plain
language. The card only collects the text and shows progress / messages; the
form view sends the text to the backend and fills its fields with the answer.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from frontend import form_theme as theme
from frontend.widgets.form_parts import StatusBanner

EXAMPLES = (
    "Sentinel-2 NDVI for Faisalabad from June to August 2024, under 20% clouds",
    "Water bodies around Mangla Dam in 2023 using Sentinel-1 radar",
    "Land surface temperature of Lahore for the last three summers",
    "Land cover change in Islamabad between 2018 and 2024",
)
BUTTON_SIZE = 58
PANEL_WIDTH = 400
MARGIN = 22


def _shadow(widget: QWidget, blur: int, alpha: int, y: int) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y)
    effect.setColor(theme.qcolor("#1E5A57", alpha))
    widget.setGraphicsEffect(effect)


class QueryAssistant(QObject):
    """Owns the floating button and its pop-up card, both drawn on top of ``host``.

    ``anchor`` is the widget whose bottom-right corner the button sticks to
    (the form's scroll area, so it stays clear of the action bar).
    """

    submitted = pyqtSignal(str)

    def __init__(self, host: QWidget, anchor: QWidget, max_length: int):
        super().__init__(host)
        self._host, self._anchor, self._max_length = host, anchor, max_length

        # ---- floating button
        self.button = QPushButton(host)
        self.button.setObjectName("AssistantButton")
        self.button.setIcon(QIcon(theme.SPARKLE_WHITE_ICON))
        self.button.setIconSize(QSize(26, 26))
        self.button.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
        self.button.setCheckable(True)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setToolTip("Describe your request and let Gemini fill the form (Ctrl+K)")
        _shadow(self.button, 24, 70, 6)

        # ---- pop-up card
        self.panel = QFrame(host)
        self.panel.setObjectName("AssistantPanel")
        self.panel.setFixedWidth(PANEL_WIDTH)
        _shadow(self.panel, 46, 50, 12)

        title = QLabel("Ask GEE-Assist")
        title.setObjectName("AssistantTitle")
        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("AssistantClose")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setToolTip("Close (Esc)")
        header = QHBoxLayout()
        header.addWidget(title, 1)
        header.addWidget(self.close_button)

        self.input = QPlainTextEdit()
        self.input.setObjectName("AssistantInput")
        self.input.setPlaceholderText(
            "What do you need? e.g. Sentinel-2 NDVI for Faisalabad, June to August 2024. "
            "Gemini fills the form for you to check."
        )
        self.input.setFixedHeight(84)

        # Examples live in a small menu instead of a permanent drop-down.
        self.examples_button = QPushButton("Examples")
        self.examples_button.setObjectName("AssistantLink")
        self.examples_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.examples_menu = QMenu(self.examples_button)
        self.examples_menu.setObjectName("AssistantMenu")
        for example in EXAMPLES:
            self.examples_menu.addAction(example, lambda text=example: self._use_example(text))
        self.examples_button.setMenu(self.examples_menu)

        self.busy_bar = QProgressBar()
        self.busy_bar.setObjectName("BusyBar")
        self.busy_bar.setRange(0, 0)  # indeterminate
        self.busy_bar.setTextVisible(False)
        self.busy_bar.hide()

        self.banner = StatusBanner()

        self.counter = QLabel()  # shown only near the limit
        self.counter.setObjectName("FieldHint")
        self.fill_button = QPushButton("Fill the form")
        self.fill_button.setObjectName("PrimaryButton")
        self.fill_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fill_button.setToolTip("Ctrl+Enter")
        footer = QHBoxLayout()
        footer.addWidget(self.examples_button)
        footer.addStretch(1)
        footer.addWidget(self.counter)
        footer.addWidget(self.fill_button)

        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self.input)
        layout.addWidget(self.busy_bar)
        layout.addWidget(self.banner)
        layout.addLayout(footer)
        self.panel.hide()

        # ---- behaviour
        self.button.toggled.connect(self._set_open)
        self.close_button.clicked.connect(self.close)
        self.fill_button.clicked.connect(self._submit)
        self.input.textChanged.connect(self._update_counter)
        QShortcut(QKeySequence("Ctrl+K"), host, activated=self.toggle)
        QShortcut(QKeySequence("Ctrl+Return"), self.panel, activated=self._submit)
        QShortcut(QKeySequence("Escape"), self.panel, activated=self.close)
        host.installEventFilter(self)
        anchor.installEventFilter(self)

        self._update_counter()
        self._place()

    # ------------------------------------------------------------------ API
    def open(self) -> None:
        self.button.setChecked(True)

    def close(self) -> None:
        self.button.setChecked(False)

    def toggle(self) -> None:
        self.button.setChecked(not self.button.isChecked())

    def is_open(self) -> bool:
        return self.panel.isVisible()

    def set_busy(self, busy: bool) -> None:
        self.busy_bar.setVisible(busy)
        self.fill_button.setEnabled(not busy)
        self.fill_button.setText("Reading your request…" if busy else "Fill the form")
        self.input.setReadOnly(busy)
        self.examples_button.setEnabled(not busy)
        if busy:
            self.banner.clear()
        self._place()

    def show_error(self, text: str) -> None:
        self.banner.show_error(text)
        self._place()

    def show_info(self, text: str) -> None:
        self.banner.show_info(text)
        self._place()

    def text(self) -> str:
        return self.input.toPlainText()

    # ------------------------------------------------------------- internals
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt API)
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show):
            self._place()
        return False

    def _set_open(self, open_: bool) -> None:
        self.panel.setVisible(open_)
        self._place()
        if open_:
            self.input.setFocus()

    def _place(self) -> None:
        """Keep the button in the anchor's bottom-right corner and the card just above it."""
        area = self._anchor.geometry()  # in host coordinates
        x = area.right() - BUTTON_SIZE - MARGIN - 8  # a little clear of the scroll bar
        y = area.bottom() - BUTTON_SIZE - MARGIN
        self.button.move(x, y)
        self.button.raise_()

        if self.panel.isVisible():
            height = min(self.panel.sizeHint().height(), y - area.top() - 24)
            self.panel.setFixedHeight(max(height, 160))
            self.panel.move(x + BUTTON_SIZE - PANEL_WIDTH, y - self.panel.height() - 14)
            self.panel.raise_()

    def _submit(self) -> None:
        if not self.fill_button.isEnabled():
            return
        text = self.text().strip()
        if not text:
            self.show_error("Type what you need first, e.g. a place, dates and what to look at.")
            self.input.setFocus()
            return
        if len(text) > self._max_length:
            self.show_error(f"Please shorten the request to {self._max_length} characters.")
            return
        self.submitted.emit(text)

    def _use_example(self, text: str) -> None:
        self.input.setPlainText(text)
        self.input.setFocus()

    def _update_counter(self) -> None:
        length = len(self.input.toPlainText())
        near_limit = length > self._max_length * 0.8
        self.counter.setVisible(near_limit)
        self.counter.setText(f"{length} / {self._max_length}")
        self.counter.setStyleSheet(f"color: {theme.ERROR};" if length > self._max_length else "")
