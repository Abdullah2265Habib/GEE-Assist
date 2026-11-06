"""Dashboard shown right after signing in: a greeting and one card per workspace.

Only "Query Input" opens something for now; the other cards are placeholders for
the use cases that are not built yet (download, analysis, reports).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from backend.dto.user_dto import UserDTO
from frontend import theme
from frontend.widgets.form_widgets import add_soft_shadow

TILE_WIDTH = 330

STYLESHEET = f"""
QFrame#DashboardTile {{
    background: {theme.WHITE};
    border: 1px solid {theme.BORDER};
    border-radius: 16px;
}}
QFrame#DashboardTile[enabled="false"] {{ background: #FAFCFB; }}
QLabel#TileBadge {{
    color: {theme.WHITE};
    font-size: 16pt;
    border-radius: 22px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {theme.LEAF}, stop:1 {theme.OCEAN});
}}
QLabel#TileBadge:disabled {{ background: {theme.MINT}; color: {theme.SUBTLE}; }}
QLabel#TileTitle {{ font-family: "{theme.SERIF}"; font-size: 14pt; color: {theme.INK}; }}
QLabel#TileTitle:disabled {{ color: {theme.MUTED}; }}
QLabel#ComingSoon {{
    color: {theme.MUTED}; background: {theme.FOAM}; border: 1px solid {theme.BORDER};
    border-radius: 9px; padding: 2px 9px; font-size: 8.5pt;
}}
"""


class DashboardTile(QFrame):
    """One workspace card: badge, title, short description and an action button."""

    def __init__(self, glyph: str, title: str, text: str, action: str | None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DashboardTile")
        self.setFixedWidth(TILE_WIDTH)
        add_soft_shadow(self)

        badge = QLabel(glyph, objectName="TileBadge")
        badge.setFixedSize(44, 44)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label = QLabel(title, objectName="TileTitle")
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(badge)
        head.addWidget(title_label, 1)

        description = QLabel(text, objectName="Muted")
        description.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)
        layout.addLayout(head)
        layout.addWidget(description)
        layout.addStretch(1)

        self.button: QPushButton | None = None
        if action:
            self.button = QPushButton(action, objectName="PrimaryButton")
            self.button.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignLeft)
        else:
            self.setEnabled(False)
            layout.addWidget(QLabel("Coming soon", objectName="ComingSoon"), 0, Qt.AlignmentFlag.AlignLeft)


class DashboardView(QWidget):
    """Start page after sign-in. Emits ``open_query_input`` when its card's button is pressed."""

    open_query_input = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(STYLESHEET)

        self.greeting = QLabel(objectName="Title")
        subtitle = QLabel("Choose what you want to work on.", objectName="Subtitle")

        self.query_tile = DashboardTile(
            "✦", "Query Input",
            "Describe a request in plain language or fill the parameter form: dataset, "
            "area of interest, dates and analysis.",
            "Open Query Input",
        )
        tiles = (
            self.query_tile,
            DashboardTile("⤓", "Download", "Fetch the requested imagery from Google Earth Engine as GeoTIFF.", None),
            DashboardTile("◔", "Analysis", "Run indices, classification and change detection on your data.", None),
            DashboardTile("☰", "Reports", "Collect maps, charts and explanations into a report.", None),
        )
        grid = QGridLayout()
        grid.setSpacing(20)
        for i, tile in enumerate(tiles):
            grid.addWidget(tile, i // 2, i % 2)

        column = QVBoxLayout()
        column.setSpacing(6)
        column.addWidget(self.greeting)
        column.addWidget(subtitle)
        column.addSpacing(22)
        column.addLayout(grid)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addLayout(column)
        row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(2)

        assert self.query_tile.button is not None
        self.query_tile.button.clicked.connect(self.open_query_input)

    def set_user(self, user: UserDTO) -> None:
        first_name = (user.full_name or "").split(" ")[0] or "there"
        self.greeting.setText(f"Welcome, {first_name}")
