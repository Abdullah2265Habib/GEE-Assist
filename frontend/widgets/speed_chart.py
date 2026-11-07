"""Download speed over the last minute: current speed as a blue area, the average speed as a green line.

Each sample is stamped with the time it was taken and drawn at that time, so the
chart keeps a true one-minute scale even when refreshes are late or the page was
hidden for a while.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Callable

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from frontend import theme

SPAN_SECONDS = 60.0


class SpeedChart(QWidget):
    def __init__(self, parent: QWidget | None = None, clock: Callable[[], float] = time.monotonic):
        super().__init__(parent)
        self._clock = clock
        self._points: deque[tuple[float, float, float]] = deque()  # (time, speed, average speed)
        self.setMinimumSize(320, 120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setToolTip("Download speed over the last minute (blue) and the download's average speed (green)")

    def add_sample(self, bytes_per_second: float, average_bytes_per_second: float = 0.0) -> None:
        now = self._clock()
        self._points.append((now, max(0.0, bytes_per_second), max(0.0, average_bytes_per_second)))
        while len(self._points) > 1 and self._points[1][0] <= now - SPAN_SECONDS:
            self._points.popleft()  # keep one point just off the left edge so the line reaches it
        self.update()

    def samples(self) -> list[float]:
        return [speed for _, speed, _ in self._points]

    def averages(self) -> list[float]:
        return [average for _, _, average in self._points]

    # ------------------------------------------------------------- painting
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.setBrush(QColor(theme.FIELD_BG))
        painter.drawRoundedRect(area, 8, 8)

        plot = area.adjusted(8, 10, -8, -8)
        painter.setPen(QPen(QColor(theme.CHART_GRID), 1, Qt.PenStyle.DashLine))
        for step in (0.25, 0.5, 0.75):
            y = plot.top() + plot.height() * step
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        if self._points:
            now = self._clock()
            times = [t for t, _, _ in self._points]
            speeds, averages = self.samples(), self.averages()
            top = max(max(speeds), max(averages), 1.0) * 1.15
            speed_line = _line(times, speeds, plot, top, now)
            average_line = _line(times, averages, plot, top, now)

            fill = QPainterPath(speed_line)
            fill.lineTo(speed_line.currentPosition().x(), plot.bottom())
            fill.lineTo(_x(times[0], plot, now), plot.bottom())
            fill.closeSubpath()
            gradient = QLinearGradient(plot.topLeft(), plot.bottomLeft())
            gradient.setColorAt(0.0, theme.color(theme.OCEAN, 110))
            gradient.setColorAt(1.0, theme.color(theme.OCEAN, 25))
            painter.save()
            painter.setClipRect(plot)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawPath(fill)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(theme.color(theme.OCEAN, 200), 1.6))
            painter.drawPath(speed_line)
            painter.setPen(QPen(QColor(theme.LEAF), 2.0))
            painter.drawPath(average_line)
            painter.restore()
        painter.end()


def _x(moment: float, plot: QRectF, now: float) -> float:
    return plot.right() - plot.width() * (now - moment) / SPAN_SECONDS


def _line(times: list[float], values: list[float], plot: QRectF, top: float, now: float) -> QPainterPath:
    path = QPainterPath()
    for i, (moment, value) in enumerate(zip(times, values)):
        point = QPointF(_x(moment, plot, now), plot.bottom() - plot.height() * (value / top))
        if i == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    return path
