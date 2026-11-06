"""Download speed over the last minute: current speed as a blue area, its average as a green line."""

from __future__ import annotations

from collections import deque

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from frontend import theme

SAMPLES = 120          # one sample per refresh (0.5 s) -> one minute
AVERAGE_OVER = 10      # samples in the moving average


class SpeedChart(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._speeds: deque[float] = deque([0.0] * SAMPLES, maxlen=SAMPLES)
        self.setMinimumSize(320, 120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setToolTip("Download speed over the last minute (blue) and its average (green)")

    def add_sample(self, bytes_per_second: float) -> None:
        self._speeds.append(max(0.0, bytes_per_second))
        self.update()

    def samples(self) -> list[float]:
        return list(self._speeds)

    def averages(self) -> list[float]:
        values, result = list(self._speeds), []
        for i in range(len(values)):
            window = values[max(0, i - AVERAGE_OVER + 1): i + 1]
            result.append(sum(window) / len(window))
        return result

    # ------------------------------------------------------------- painting
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.setBrush(QColor("#FBFDFC"))
        painter.drawRoundedRect(area, 8, 8)

        plot = area.adjusted(8, 10, -8, -8)
        painter.setPen(QPen(QColor("#E3EEEA"), 1, Qt.PenStyle.DashLine))
        for step in (0.25, 0.5, 0.75):
            y = plot.top() + plot.height() * step
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        speeds, averages = self.samples(), self.averages()
        top = max(max(speeds), 1.0) * 1.15
        speed_line = _line(speeds, plot, top)
        average_line = _line(averages, plot, top)

        fill = QPainterPath(speed_line)
        fill.lineTo(plot.right(), plot.bottom())
        fill.lineTo(plot.left(), plot.bottom())
        fill.closeSubpath()
        gradient = QLinearGradient(plot.topLeft(), plot.bottomLeft())
        gradient.setColorAt(0.0, theme.color(theme.OCEAN, 110))
        gradient.setColorAt(1.0, theme.color(theme.OCEAN, 25))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(fill)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(theme.color(theme.OCEAN, 200), 1.6))
        painter.drawPath(speed_line)
        painter.setPen(QPen(QColor(theme.LEAF), 2.0))
        painter.drawPath(average_line)
        painter.end()


def _line(values: list[float], plot: QRectF, top: float) -> QPainterPath:
    path = QPainterPath()
    step = plot.width() / max(len(values) - 1, 1)
    for i, value in enumerate(values):
        point = QPointF(plot.left() + i * step, plot.bottom() - plot.height() * (value / top))
        if i == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    return path
