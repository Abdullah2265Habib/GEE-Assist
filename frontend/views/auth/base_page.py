from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from backend.business.facade import IBusinessFacade
from frontend.widgets.form_widgets import Banner


class AuthPage(QWidget):
    """A page inside the auth card: title, subtitle, banner, then the page's own content."""

    def __init__(self, facade: IBusinessFacade, title: str, subtitle: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._facade = facade

        self.title = QLabel(title, objectName="Title")
        self.title.setWordWrap(True)
        self.subtitle = QLabel(subtitle, objectName="Subtitle")
        self.subtitle.setWordWrap(True)
        self.banner = Banner()

        header = QVBoxLayout()
        header.setContentsMargins(0, 0, 0, 6)
        header.setSpacing(6)
        header.addWidget(self.title)
        header.addWidget(self.subtitle)

        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(14)
        self.body.addLayout(header)
        self.body.addWidget(self.banner)

    def reset(self) -> None:
        """Called whenever the page is shown again; clears messages."""
        self.banner.clear()


def centered_row(*widgets: QWidget, spacing: int = 4) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(spacing)
    row.addStretch(1)
    for widget in widgets:
        row.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
    row.addStretch(1)
    return row
