"""Small fade helpers for whole widgets."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QWidget


def fade_in(widget: QWidget, duration_ms: int = 600) -> QPropertyAnimation:
    """Fade ``widget`` from transparent to opaque.

    The opacity effect is removed afterwards: a permanent QGraphicsOpacityEffect would make Qt
    render the widget (and its children, e.g. animated GIFs) off-screen on every repaint.
    """
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)

    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration_ms)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.finished.connect(lambda: widget.setGraphicsEffect(None))
    animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return animation
