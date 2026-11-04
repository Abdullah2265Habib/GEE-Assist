"""Form building blocks shared by the sign-in / sign-up pages."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QMovie
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from frontend import theme
from frontend.widgets.icons import eye_icon


class FormField(QWidget):
    """Label + line edit + (hint or error) line underneath."""

    def __init__(self, label: str, placeholder: str = "", hint: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._hint = hint

        self.label = QLabel(label, objectName="FieldLabel")
        self.input = QLineEdit()
        self.input.setPlaceholderText(placeholder)
        self.input.setClearButtonEnabled(False)
        self.input.textEdited.connect(lambda _: self.clear_error())
        self.label.setBuddy(self.input)

        self.message = QLabel(hint, objectName="FieldHint")
        self.message.setWordWrap(True)
        self.message.setVisible(bool(hint))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(self.label)
        layout.addWidget(self.input)
        layout.addWidget(self.message)

    def text(self) -> str:
        return self.input.text()

    def set_text(self, value: str) -> None:
        self.input.setText(value)

    def set_error(self, message: str) -> None:
        self.message.setObjectName("FieldError")
        self.message.setText(message)
        self.message.setVisible(True)
        self._set_invalid(True)

    def clear_error(self) -> None:
        if not self.input.property("invalid"):
            return
        self.message.setObjectName("FieldHint")
        self.message.setText(self._hint)
        self.message.setVisible(bool(self._hint))
        self._set_invalid(False)

    def has_error(self) -> bool:
        return bool(self.input.property("invalid"))

    def _set_invalid(self, invalid: bool) -> None:
        self.input.setProperty("invalid", invalid)
        for widget in (self.input, self.message):
            widget.style().unpolish(widget)
            widget.style().polish(widget)


class PasswordField(FormField):
    """FormField with hidden text and an eye button to show / hide it."""

    def __init__(self, label: str, placeholder: str = "", hint: str = "", parent: QWidget | None = None):
        super().__init__(label, placeholder, hint, parent)
        self.input.setEchoMode(QLineEdit.EchoMode.Password)
        self._toggle = self.input.addAction(eye_icon(False), QLineEdit.ActionPosition.TrailingPosition)
        self._toggle.setToolTip("Show password")
        self._toggle.triggered.connect(self._toggle_visibility)

    def _toggle_visibility(self) -> None:
        hidden = self.input.echoMode() == QLineEdit.EchoMode.Password
        self.input.setEchoMode(QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password)
        self._toggle.setIcon(eye_icon(hidden))
        self._toggle.setToolTip("Hide password" if hidden else "Show password")


class Banner(QLabel):
    """Coloured message box (error / success / info). Hidden when empty."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.hide()

    def show_error(self, text: str) -> None:
        self._show("ErrorBanner", text)

    def show_success(self, text: str) -> None:
        self._show("SuccessBanner", text)

    def show_info(self, text: str) -> None:
        self._show("InfoBanner", text)

    def clear(self) -> None:  # noqa: D401 - QLabel API
        super().clear()
        self.hide()

    def _show(self, kind: str, text: str) -> None:
        self.setObjectName(kind)
        self.setText(text)
        self.style().unpolish(self)
        self.style().polish(self)
        self.show()


class BusyButton(QPushButton):
    """Button that shows a "working" label and disables itself while a request runs."""

    def __init__(self, text: str, busy_text: str, object_name: str = "PrimaryButton", parent: QWidget | None = None):
        super().__init__(text, parent)
        self._idle_text = text
        self._busy_text = busy_text
        self.setObjectName(object_name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(44)

    def set_busy(self, busy: bool) -> None:
        self.setEnabled(not busy)
        self.setText(self._busy_text if busy else self._idle_text)


def link_button(text: str, parent: QWidget | None = None) -> QPushButton:
    button = QPushButton(text, parent)
    button.setObjectName("LinkButton")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFlat(True)
    return button


def add_soft_shadow(widget: QWidget, blur: int = 48, alpha: int = 34, y_offset: int = 12) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    shadow.setColor(theme.color("#1E5A57", alpha))
    widget.setGraphicsEffect(shadow)


def h_line() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"color: {theme.BORDER}; background: {theme.BORDER}; max-height: 1px;")
    return line


class LoopingGif(QLabel):
    """Shows an animated GIF that loops forever, scaled smoothly to ``width``."""

    def __init__(self, path: Path, width: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._movie = QMovie(str(path), parent=self)
        self._movie.setCacheMode(QMovie.CacheMode.CacheAll)
        if not self._movie.isValid():
            return
        self._movie.jumpToFrame(0)
        native = self._movie.currentImage().size()
        if native.width() > 0:
            self._movie.setScaledSize(QSize(width, round(width * native.height() / native.width())))
        # GIFs may stop after their own loop count - restart so it truly loops.
        self._movie.finished.connect(self._movie.start)
        self.setMovie(self._movie)
        self.setFixedHeight(self._movie.scaledSize().height())
        self._movie.start()

    def set_playing(self, playing: bool) -> None:
        self._movie.setPaused(not playing)
