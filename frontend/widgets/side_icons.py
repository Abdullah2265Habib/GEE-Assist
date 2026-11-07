"""Small drawn icons for the side bar, each with a looping animation.

An icon is drawn for a moment ``t`` of its loop (0 to 1). At rest (not hovered) it is
drawn at ``t = None``: a still picture. Colours come from the theme, so the icons
follow light and dark themes.

* ``DownloadIcon``: an arrow over a tray; animated, the arrow slides down into the
  tray and comes back in from the top (it wraps around).
* ``WritingIcon``: a sheet of paper and a pencil; animated, the pencil writes the
  lines on the paper one after another.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen

from frontend import theme


class SideIcon:
    """An icon drawn in a square ``rect``; ``period_ms`` is the length of one animation loop."""

    period_ms = 1200

    def paint(self, painter: QPainter, rect: QRectF, t: float | None) -> None:
        raise NotImplementedError


class DownloadIcon(SideIcon):
    period_ms = 1100

    def paint(self, painter: QPainter, rect: QRectF, t: float | None) -> None:
        s = rect.width()
        pen = QPen(QColor(theme.INK), max(1.6, s * 0.09), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                   Qt.PenJoinStyle.RoundJoin)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Tray: a U along the bottom.
        painter.setPen(pen)
        tray_top, bottom = rect.top() + s * 0.62, rect.top() + s * 0.86
        tray = QPainterPath(QPointF(rect.left() + s * 0.14, tray_top))
        tray.lineTo(rect.left() + s * 0.14, bottom)
        tray.lineTo(rect.right() - s * 0.14, bottom)
        tray.lineTo(rect.right() - s * 0.14, tray_top)
        painter.drawPath(tray)

        # Arrow: slides down by one "lane" per loop; a second copy above makes it wrap around.
        lane = QRectF(rect.left(), rect.top(), s, s * 0.74)  # the arrow is only seen above the tray's floor
        travel = lane.height()
        offset = (t or 0.0) * travel
        painter.setClipRect(lane)
        arrow_pen = QPen(pen)
        arrow_pen.setColor(QColor(theme.LEAF))
        painter.setPen(arrow_pen)
        for shift in (offset, offset - travel):
            self._arrow(painter, rect, shift)
        painter.restore()

    @staticmethod
    def _arrow(painter: QPainter, rect: QRectF, shift: float) -> None:
        s, x = rect.width(), rect.center().x()
        top, tip = rect.top() + s * 0.12 + shift, rect.top() + s * 0.6 + shift
        painter.drawLine(QPointF(x, top), QPointF(x, tip))
        head = QPainterPath(QPointF(x - s * 0.2, tip - s * 0.2))
        head.lineTo(x, tip)
        head.lineTo(x + s * 0.2, tip - s * 0.2)
        painter.drawPath(head)

    @staticmethod
    def arrow_tip(rect: QRectF, t: float | None) -> float:
        """Where the arrow's tip is at moment ``t`` (for tests): it moves down, then wraps."""
        s = rect.width()
        return rect.top() + s * 0.6 + (t or 0.0) * s * 0.74


class WritingIcon(SideIcon):
    period_ms = 2100
    LINES = 3

    def paint(self, painter: QPainter, rect: QRectF, t: float | None) -> None:
        s = rect.width()
        line_width = max(1.4, s * 0.075)
        pen = QPen(QColor(theme.INK), line_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                   Qt.PenJoinStyle.RoundJoin)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Paper.
        paper = QRectF(rect.left() + s * 0.08, rect.top() + s * 0.06, s * 0.62, s * 0.86)
        painter.setPen(pen)
        painter.setBrush(QColor(theme.WHITE))
        painter.drawRoundedRect(paper, s * 0.08, s * 0.08)

        # Writing: at rest every line is written; animated, the lines are written one by one.
        writing = QPen(QColor(theme.MUTED), line_width * 0.85, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(writing)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        tip = None
        for line in range(self.LINES):
            done = self.line_progress(t, line)
            if done <= 0:
                continue
            start, end = self._line_ends(paper, line)
            length = (end.x() - start.x()) * done
            path = QPainterPath(start)
            steps = max(2, int(length / max(1.0, s * 0.04)))
            for step in range(1, steps + 1):
                x = start.x() + length * step / steps
                path.lineTo(x, start.y() + math.sin((x - start.x()) / (s * 0.05)) * s * 0.025)  # handwriting
            painter.drawPath(path)
            if 0 < done < 1 or t is None:
                tip = path.currentPosition()
        if tip is None:  # between lines: the pencil waits at the start of the next one
            tip, _ = self._line_ends(paper, min(self.LINES - 1, int((t or 0) * self.LINES)))

        self._pencil(painter, rect, tip, line_width)
        painter.restore()

    @classmethod
    def line_progress(cls, t: float | None, line: int) -> float:
        """How much of ``line`` is written at moment ``t`` (0 to 1). At rest, all of it."""
        if t is None:
            return 1.0
        return min(1.0, max(0.0, t * cls.LINES - line))

    @staticmethod
    def _line_ends(paper: QRectF, line: int) -> tuple[QPointF, QPointF]:
        y = paper.top() + paper.height() * (0.3 + 0.22 * line)
        return QPointF(paper.left() + paper.width() * 0.2, y), QPointF(paper.right() - paper.width() * 0.2, y)

    @staticmethod
    def _pencil(painter: QPainter, rect: QRectF, tip: QPointF, line_width: float) -> None:
        """A pencil leaning to the right, its point at ``tip``."""
        s = rect.width()
        painter.save()
        painter.translate(tip)
        painter.rotate(-45)  # the pencil points down-left, its body up-right
        length, width = s * 0.62, s * 0.2
        body = QRectF(width * 0.9, -width / 2, length - width * 0.9, width)
        painter.setPen(QPen(QColor(theme.INK), line_width * 0.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(QColor(theme.OCEAN))
        painter.drawRoundedRect(body, width * 0.25, width * 0.25)
        point = QPainterPath(QPointF(0, 0))  # sharpened end
        point.lineTo(width * 0.9, -width / 2)
        point.lineTo(width * 0.9, width / 2)
        point.closeSubpath()
        painter.setBrush(QColor(theme.WHITE))
        painter.drawPath(point)
        painter.restore()
