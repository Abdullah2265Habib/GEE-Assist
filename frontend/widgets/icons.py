"""Small icons drawn with QPainter, so they stay sharp at any DPI and need no image files."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from frontend import theme

_SIZE = 64  # drawn large, Qt scales it down smoothly


def _canvas() -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pixmap, painter


def eye_icon(visible: bool, color: str = theme.MUTED) -> QIcon:
    pixmap, p = _canvas()
    pen = QPen(QColor(color), 4.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    outline = QPainterPath()
    outline.moveTo(6, 32)
    outline.quadTo(32, 6, 58, 32)
    outline.quadTo(32, 58, 6, 32)
    p.drawPath(outline)
    p.drawEllipse(QPointF(32, 32), 8.5, 8.5)
    if not visible:
        p.drawLine(QPointF(12, 52), QPointF(52, 12))
    p.end()
    return QIcon(pixmap)


def google_icon() -> QIcon:
    """The multi-coloured "G" used on "Continue with Google" buttons."""
    pixmap, p = _canvas()
    rect = QRectF(10, 10, 44, 44)
    width = 9.0

    def arc(color: str, start: float, span: float) -> None:
        p.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawArc(rect, int(start * 16), int(span * 16))

    arc("#EA4335", 45, 95)     # red: top
    arc("#FBBC05", 140, 85)    # yellow: left
    arc("#34A853", 225, 100)   # green: bottom
    arc("#4285F4", 325, 35)    # blue: lower right
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#4285F4"))
    p.drawRect(QRectF(32, 27.5, 26.5, 9))  # blue bar
    p.end()
    return QIcon(pixmap)


def envelope_pixmap(size: int = 76) -> QPixmap:
    """Mail icon on a soft green-blue disc (verification page)."""
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(theme.MINT))
    p.drawEllipse(QRectF(0, 0, size, size))
    p.setBrush(QColor(theme.SKY))
    p.drawEllipse(QRectF(size * 0.12, size * 0.12, size * 0.76, size * 0.76))

    w, h = size * 0.46, size * 0.32
    x, y = (size - w) / 2, (size - h) / 2
    p.setBrush(QColor(theme.WHITE))
    p.setPen(QPen(QColor(theme.LEAF), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawRoundedRect(QRectF(x, y, w, h), 3, 3)
    flap = QPainterPath()
    flap.moveTo(x + 2, y + 2)
    flap.lineTo(x + w / 2, y + h * 0.58)
    flap.lineTo(x + w - 2, y + 2)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(theme.OCEAN), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawPath(flap)
    p.end()
    return pixmap
