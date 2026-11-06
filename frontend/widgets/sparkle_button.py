"""Round button with a sparkle that comes alive on hover.

The sparkle (one big and one small four-point star, same shape as
``resources/icons/sparkle_white.svg``) is painted here instead of being an
icon, so it can move: while the pointer is over the button the two stars
twinkle out of step and small glints appear and fade inside the circle. When
the pointer leaves, everything settles back to the still sparkle.

The background still comes from the stylesheet, and ``iconSize`` still sets
how big the sparkle is drawn, so animating ``iconSize`` works as before.
"""

from __future__ import annotations

import math
import random

from PyQt6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QRadialGradient
from PyQt6.QtWidgets import QPushButton, QWidget

FRAME_MS = 16           # ~60 fps while animating
FADE_S = 0.25           # how long the hover effect takes to fade in / out
GLINT_EVERY_S = 0.11    # a new glint this often while hovered
GLINT_LIFE_S = (0.55, 0.95)
GLINT_SIZE = (1.6, 3.4)  # radius in px


def _star(cx: float, cy: float, r: float) -> QPainterPath:
    """Four-point star with curved sides, centred on (cx, cy) with "radius" r."""
    a, b = 0.07 * r, 0.44 * r
    path = QPainterPath(QPointF(cx, cy - r))
    path.cubicTo(cx + a, cy - b, cx + b, cy - a, cx + r, cy)
    path.cubicTo(cx + b, cy + a, cx + a, cy + b, cx, cy + r)
    path.cubicTo(cx - a, cy + b, cx - b, cy + a, cx - r, cy)
    path.cubicTo(cx - b, cy - a, cx - a, cy - b, cx, cy - r)
    return path


class _Glint:
    __slots__ = ("x", "y", "size", "born", "life")

    def __init__(self, x: float, y: float, size: float, born: float, life: float):
        self.x, self.y, self.size, self.born, self.life = x, y, size, born, life


class SparkleButton(QPushButton):
    """Checkable round button whose sparkle twinkles while hovered."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._hovered = False
        self._glow = 0.0          # 0 = still, 1 = fully animated
        self._glints: list[_Glint] = []
        self._next_glint = 0.0
        self._last = 0.0
        self._rng = random.Random()
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------- hover
    def enterEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().enterEvent(event)
        self.set_hovered(True)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().leaveEvent(event)
        self.set_hovered(False)

    def set_hovered(self, hovered: bool) -> None:
        self._hovered = hovered
        if hovered and not self._timer.isActive():
            self._last = self._now()
            self._next_glint = self._last
            self._timer.start()

    def is_animating(self) -> bool:
        return self._timer.isActive()

    # ------------------------------------------------------------- frames
    def _now(self) -> float:
        return self._clock.elapsed() / 1000.0

    def _tick(self) -> None:
        now = self._now()
        dt, self._last = now - self._last, now

        step = dt / FADE_S
        self._glow = min(1.0, self._glow + step) if self._hovered else max(0.0, self._glow - step)

        if self._hovered:
            while self._next_glint <= now:
                self._spawn_glint(self._next_glint)
                self._next_glint += GLINT_EVERY_S
        self._glints = [g for g in self._glints if now - g.born < g.life]

        if not self._hovered and self._glow == 0.0 and not self._glints:
            self._timer.stop()
        self.update()

    def _spawn_glint(self, born: float) -> None:
        # Anywhere inside the inner part of the circle (uniform over the disc).
        radius = 0.36 * min(self.width(), self.height()) * math.sqrt(self._rng.random())
        angle = self._rng.uniform(0, 2 * math.pi)
        centre = QRectF(self.rect()).center()
        self._glints.append(_Glint(
            centre.x() + radius * math.cos(angle),
            centre.y() + radius * math.sin(angle),
            self._rng.uniform(*GLINT_SIZE),
            born,
            self._rng.uniform(*GLINT_LIFE_S),
        ))

    # ------------------------------------------------------------- paint
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().paintEvent(event)  # stylesheet background (round gradient)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect())
        circle = QPainterPath()
        circle.addEllipse(bounds)
        painter.setClipPath(circle)
        painter.setPen(Qt.PenStyle.NoPen)

        now, glow = self._now(), self._glow
        centre = bounds.center()

        if glow > 0:
            # Soft light behind the sparkle.
            halo = QRadialGradient(centre, bounds.width() * 0.5)
            halo.setColorAt(0.0, QColor(255, 255, 255, int(70 * glow)))
            halo.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(halo)
            painter.drawEllipse(bounds)

        # The sparkle itself, laid out on the icon's 24-unit grid.
        unit = self.iconSize().width() / 24.0
        left, top = centre.x() - 12 * unit, centre.y() - 12 * unit
        big = 1 + 0.12 * glow * math.sin(2 * math.pi * now / 1.4)
        small = 1 + 0.40 * glow * math.sin(2 * math.pi * now / 0.9 + 1.3)
        small_alpha = 255 - int(90 * glow * (0.5 - 0.5 * math.sin(2 * math.pi * now / 0.9 + 1.3)))

        painter.setBrush(QColor(255, 255, 255))
        painter.drawPath(_star(left + 10 * unit, top + 9.5 * unit, 7 * unit * big))
        painter.setBrush(QColor(255, 255, 255, small_alpha))
        painter.drawPath(_star(left + 18.5 * unit, top + 16.5 * unit, 3.5 * unit * small))

        # Glints: grow and fade in, then shrink and fade out.
        for g in self._glints:
            phase = math.sin(math.pi * min(1.0, (now - g.born) / g.life))
            painter.setBrush(QColor(255, 255, 255, int(235 * phase * max(glow, 0.35))))
            painter.drawPath(_star(g.x, g.y, g.size * (0.4 + 0.6 * phase)))
        painter.end()
