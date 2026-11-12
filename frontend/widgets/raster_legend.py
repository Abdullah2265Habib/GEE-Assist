"""How to read a raster view: a colour bar with its range, class swatches, or the RGB bands."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from backend.dto.map_dto import LegendDTO
from frontend import theme

RGB_CHANNELS = (("Red", "#E0453A"), ("Green", "#3DAA5C"), ("Blue", "#3A7BE0"))


def format_value(value: float | None) -> str:
    """A band or index value, as briefly as it reads well (e.g. 0.42, 1530, 4.5e-05)."""
    if value is None:
        return "no data"
    magnitude = abs(value)
    if magnitude >= 1000 or value == int(value):
        return f"{value:,.0f}"
    if magnitude >= 1:
        return f"{value:.2f}"
    if magnitude >= 0.001:
        return f"{value:.3f}"
    return f"{value:.2g}"


class ColourBar(QWidget):
    """A horizontal bar blending ``colours`` from left (low) to right (high)."""

    def __init__(self, colours: tuple[str, ...], parent: QWidget | None = None):
        super().__init__(parent)
        self.colours = colours
        self.setFixedHeight(14)
        self.setMinimumWidth(120)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)
        gradient = QLinearGradient(rect.left(), 0, rect.right(), 0)
        last = max(1, len(self.colours) - 1)
        for index, colour in enumerate(self.colours):
            gradient.setColorAt(index / last, QColor(colour))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(theme.BORDER_STRONG), 1))
        painter.drawRoundedRect(rect, 4, 4)
        painter.end()


def _swatch(colour: str) -> QLabel:
    swatch = QLabel()
    swatch.setFixedSize(14, 14)
    swatch.setStyleSheet(f"background: {colour}; border: 1px solid {theme.BORDER_STRONG}; border-radius: 3px;")
    return swatch


class RasterLegend(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.legend: LegendDTO | None = None
        self.title = QLabel(objectName="FieldLabel")
        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(6)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.title)
        layout.addLayout(self._body)

    def set_legend(self, legend: LegendDTO) -> None:
        self.legend = legend
        self.title.setText(legend.title)
        self._clear()
        if legend.kind == "scale":
            self._body.addWidget(ColourBar(legend.colours))
            ends = QHBoxLayout()
            low = QLabel(format_value(legend.low), objectName="Muted")
            high = QLabel(format_value(legend.high), objectName="Muted")
            high.setAlignment(Qt.AlignmentFlag.AlignRight)
            ends.addWidget(low)
            ends.addWidget(high)
            self._body.addLayout(ends)
        else:
            if legend.kind == "classes":
                rows = list(zip(legend.labels, legend.colours))
            else:  # "rgb": which band is shown as which colour
                rows = [(f"{channel} ← {band}", colour)
                        for (channel, colour), band in zip(RGB_CHANNELS, legend.labels)]
            grid = QGridLayout()
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(5)
            for row, (label, colour) in enumerate(rows):
                grid.addWidget(_swatch(colour), row, 0)
                grid.addWidget(QLabel(label), row, 1)
            grid.setColumnStretch(1, 1)
            self._body.addLayout(grid)

    def item_texts(self) -> list[str]:
        """The texts shown under the title (for tests and accessibility)."""
        texts: list[str] = []
        for label in self.findChildren(QLabel):
            if label is not self.title and label.text():
                texts.append(label.text())
        return texts

    def _clear(self) -> None:
        def remove(layout) -> None:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget() is not None:
                    item.widget().deleteLater()
                    item.widget().setParent(None)
                elif item.layout() is not None:
                    remove(item.layout())
        remove(self._body)
