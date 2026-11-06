"""Collapsible "Chat with Gemini" box for the side panel (UC-02).

A round sparkle button sits at the bottom of the side panel, under the kept
requests' parameters. Clicking it (or Ctrl+K) opens a card above it where the
user types a request in plain language; the card takes its room from the
parameters view. The card only collects the text and shows progress /
messages; the form view sends the text to the backend and fills its fields
with the answer.
"""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from frontend import form_theme as theme
from frontend.widgets.form_parts import StatusBanner
from frontend.widgets.sparkle_button import SparkleButton

EXAMPLES = (
    "Sentinel-2 NDVI for Faisalabad from June to August 2024, under 20% clouds",
    "Water bodies around Mangla Dam in 2023 using Sentinel-1 radar",
    "Land surface temperature of Lahore for the last three summers",
    "Land cover change in Islamabad between 2018 and 2024",
)
BUTTON_SIZE = 58
ICON_SIZE = 26
SLIDE_MS = 220   # card opening / closing
PULSE_MS = 260   # sparkle "tap" on the button
NO_MAX_HEIGHT = 16777215  # QWIDGETSIZE_MAX


class _Reveal(QWidget):
    """Shows its child at full size, pinned to the bottom edge, and clips the rest.

    Animating this widget's ``maximumHeight`` makes the child rise into view
    (or sink away) without squashing its layout.
    """

    def __init__(self, child: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self._child = child
        child.setParent(self)
        child.installEventFilter(self)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _natural_height(self) -> int:
        width = self.width() or (self.parentWidget().width() if self.parentWidget() else 0)
        if width and self._child.hasHeightForWidth():
            return self._child.heightForWidth(width)
        return self._child.sizeHint().height()

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        return QSize(self._child.sizeHint().width(), self._natural_height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        return QSize(self._child.minimumSizeHint().width(), 0)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        self._place()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt API)
        if obj is self._child and event.type() == QEvent.Type.LayoutRequest:
            self.updateGeometry()  # e.g. a message banner appeared in the card
            self._place()
        return False

    def _place(self) -> None:
        height = self._natural_height()
        self._child.setGeometry(0, self.height() - height, self.width(), height)


class QueryAssistant(QWidget):
    """A round sparkle button ("Chat with Gemini") with a card that opens above it.

    Meant to sit at the bottom of a vertical layout: when the card opens, the
    stretchable widgets above it shrink to make room.
    """

    submitted = pyqtSignal(str)

    def __init__(self, max_length: int, parent: QWidget | None = None):
        super().__init__(parent)
        self._max_length = max_length
        self.setObjectName("QueryAssistant")
        # Lives outside the parameter form, so it carries the form's stylesheet
        # itself (buttons, banner, input and progress bar styles).
        self.setStyleSheet(theme.FORM_STYLESHEET)

        # ---- toggle button
        self.button = SparkleButton()  # sparkle twinkles while hovered
        self.button.setObjectName("AssistantButton")
        self.button.setAccessibleName("Chat with Gemini")
        self.button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.button.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
        self.button.setCheckable(True)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setToolTip("Chat with Gemini: describe your request and let it fill the form (Ctrl+K)")

        # ---- card
        self.panel = QFrame()
        self.panel.setObjectName("AssistantPanel")

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
        # The panel is narrow, so messages wrap; wrapped labels size themselves
        # from contents margins, not stylesheet padding.
        self.banner.setContentsMargins(10, 4, 10, 4)

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
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addWidget(self.input)
        layout.addWidget(self.busy_bar)
        layout.addWidget(self.banner)
        layout.addLayout(footer)

        # The card sits in a clipping frame so it can slide up out of the button.
        self._reveal = _Reveal(self.panel)
        self._reveal.hide()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        outer.addWidget(self._reveal)
        outer.addWidget(self.button, 0, Qt.AlignmentFlag.AlignRight)

        # ---- animations: the card slides open/closed, the sparkle pulses on click
        self._slide = QPropertyAnimation(self._reveal, b"maximumHeight", self)
        self._slide.setDuration(SLIDE_MS)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide.finished.connect(self._on_slide_finished)

        self._pulse = QPropertyAnimation(self.button, b"iconSize", self)
        self._pulse.setDuration(PULSE_MS)
        self._pulse.setEasingCurve(QEasingCurve.Type.OutBack)
        self._pulse.setKeyValueAt(0.0, QSize(ICON_SIZE, ICON_SIZE))
        self._pulse.setKeyValueAt(0.4, QSize(ICON_SIZE - 8, ICON_SIZE - 8))
        self._pulse.setKeyValueAt(1.0, QSize(ICON_SIZE, ICON_SIZE))

        # ---- behaviour
        self.button.clicked.connect(self._pulse.start)
        self.button.toggled.connect(self._set_open)
        self.close_button.clicked.connect(self.collapse)
        self.fill_button.clicked.connect(self._submit)
        self.input.textChanged.connect(self._update_counter)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.toggle)
        QShortcut(QKeySequence("Ctrl+Return"), self.panel, activated=self._submit)
        QShortcut(QKeySequence("Escape"), self.panel, activated=self.collapse)

        self._update_counter()

    # ------------------------------------------------------------------ API
    def expand(self) -> None:
        self.button.setChecked(True)

    def collapse(self) -> None:
        self.button.setChecked(False)

    def toggle(self) -> None:
        self.button.setChecked(not self.button.isChecked())

    def is_open(self) -> bool:
        return self.button.isChecked()

    def set_busy(self, busy: bool) -> None:
        self.busy_bar.setVisible(busy)
        self.fill_button.setEnabled(not busy)
        self.fill_button.setText("Reading your request…" if busy else "Fill the form")
        self.input.setReadOnly(busy)
        self.examples_button.setEnabled(not busy)
        if busy:
            self.banner.clear()

    def show_error(self, text: str) -> None:
        self.banner.show_error(text)

    def show_info(self, text: str) -> None:
        self.banner.show_info(text)

    def text(self) -> str:
        return self.input.toPlainText()

    # ------------------------------------------------------------- internals
    def _set_open(self, open_: bool) -> None:
        start = self._reveal.height() if self._reveal.isVisible() else 0
        self._slide.stop()
        if open_:
            self._reveal.setMaximumHeight(start)
            self._reveal.show()
            self._slide.setStartValue(start)
            self._slide.setEndValue(self._reveal.sizeHint().height())
            self.input.setFocus()
        else:
            self._slide.setStartValue(start)
            self._slide.setEndValue(0)
        self._slide.start()

    def _on_slide_finished(self) -> None:
        if self.button.isChecked():
            # Let the card grow again when a message banner appears.
            self._reveal.setMaximumHeight(NO_MAX_HEIGHT)
        else:
            self._reveal.hide()

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
