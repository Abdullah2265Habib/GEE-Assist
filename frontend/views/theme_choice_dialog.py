"""First start-up: let the user pick the app's theme (light, dark blue-green or dark grey)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from frontend import appearance, palette, theme

SWATCH_COLOURS = ("WHITE", "INK", "LEAF", "OCEAN")  # surface, text and the two accents


class ThemeChoiceDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Choose a theme")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"QDialog {{ background: {theme.WHITE}; }}")

        title = QLabel("Choose a theme")
        title.setStyleSheet(f"font-family: '{theme.SERIF}'; font-size: 16pt; color: {theme.INK};")
        hint = QLabel("You can change it later in View → Theme.", objectName="Muted")

        self.options: dict[str, QRadioButton] = {}
        self._group = QButtonGroup(self)
        choices = QVBoxLayout()
        choices.setSpacing(10)
        for name, label in appearance.THEMES.items():
            option = QRadioButton(label)
            option.setChecked(name == appearance.DEFAULT_THEME)
            self._group.addButton(option)
            self.options[name] = option
            row = QHBoxLayout()
            row.addWidget(option, 1)
            row.addWidget(_swatches(palette.PALETTES[name]))
            choices.addLayout(row)

        self.continue_button = QPushButton("Continue", objectName="PrimaryButton")
        self.continue_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.continue_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.continue_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(choices)
        layout.addLayout(buttons)

    def chosen_theme(self) -> str:
        return next(name for name, option in self.options.items() if option.isChecked())


def _swatches(colours: dict[str, str]) -> QFrame:
    """A small preview of a theme: its surface, text and accent colours."""
    frame = QFrame()
    row = QHBoxLayout(frame)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(3)
    for key in SWATCH_COLOURS:
        swatch = QLabel()
        swatch.setFixedSize(18, 18)
        swatch.setStyleSheet(
            f"background: {colours[key]}; border: 1px solid {theme.BORDER_STRONG}; border-radius: 4px;"
        )
        row.addWidget(swatch)
    return frame


def ask_theme_on_first_run(path: Path = appearance.SETTINGS_FILE) -> bool:
    """On the first start-up, ask for a theme and save it.

    Returns True if the app must restart to use it (it chose a theme other than the
    one this run started with). Closing the window keeps the light theme.
    """
    if appearance.saved_theme(path) is not None:
        return False
    dialog = ThemeChoiceDialog()
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    name = dialog.chosen_theme() if accepted else appearance.DEFAULT_THEME
    appearance.save_theme(name, path)
    return name != palette.THEME
