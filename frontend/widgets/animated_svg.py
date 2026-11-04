"""Plays an animated (SMIL) SVG.

The Earth/satellite SVG animates with ``animateMotion``, spline timing and opacity/display
animations. Qt's own SVG renderer does not support all of it (the satellite disappears) and is
too slow for the large embedded images, so the SVG is shown through Qt WebEngine (Chromium),
which renders it exactly like a browser. Without WebEngine (or on the headless "offscreen"
platform used by the tests) it falls back to a still image drawn by QtSvg.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from html import escape
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)

_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  html, body {{ margin: 0; padding: 0; overflow: hidden; background: transparent; }}
  img {{ display: block; width: {width}px; height: {height}px; object-fit: contain;
         user-select: none; -webkit-user-drag: none; pointer-events: none;
         opacity: 0; transition: opacity {fade_ms}ms ease-out; }}
  img.shown {{ opacity: 1; }}
</style></head>
<body><img src="{src}" alt=""></body></html>"""


@lru_cache(maxsize=8)
def _still_frame(path: Path, width: int, height: int, ratio: float) -> QPixmap:
    """First frame of the SVG as a pixmap. Cached: parsing this 2 MB SVG takes ~2 s."""
    pixmap = QPixmap(round(width * ratio), round(height * ratio))
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(str(path))
    if renderer.isValid():
        renderer.setAnimationEnabled(False)
        renderer.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        renderer.render(painter)
        painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def _web_engine_view_class():
    """QWebEngineView, or None if WebEngine is missing / unusable on this platform."""
    if QGuiApplication.platformName() in ("offscreen", "minimal"):
        return None
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
    except (ImportError, RuntimeError):  # not installed, or imported after QApplication was created
        return None
    return QWebEngineView


class AnimatedSvg(QWidget):
    """Shows ``path`` at ``width`` pixels wide (height from the SVG's aspect ratio), looping forever.

    Each time the widget is shown it fades the picture in after ``reveal_delay_ms`` - set it to
    the duration of any fade running on the parent page. (A web view cannot be drawn through a
    parent's QGraphicsOpacityEffect, so it would otherwise pop in once that fade ends.)
    """

    FADE_MS = 700

    def __init__(
        self,
        path: Path,
        width: int,
        aspect_ratio: float | None = None,
        reveal_delay_ms: int = 0,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._path = path
        self._reveal_delay_ms = reveal_delay_ms
        self._loaded = False
        self._want_shown = False
        self._reveal_timer = QTimer(self, singleShot=True)
        self._reveal_timer.timeout.connect(lambda: self._set_shown(True))
        ratio = aspect_ratio or self._svg_aspect_ratio(path)
        self.setFixedSize(QSize(width, round(width * ratio)))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.uses_web_engine = False
        self._view = self._make_web_view() or self._make_svg_widget()
        layout.addWidget(self._view)

    # ------------------------------------------------------------------ backends
    def _make_web_view(self) -> QWidget | None:
        view_class = _web_engine_view_class()
        if view_class is None or not self._path.exists():
            return None
        try:
            view = view_class(self)
            # A fixed size: pages are often created hidden, and a web view laid out while hidden
            # can keep a tiny viewport.
            view.setFixedSize(self.size())
            view.page().setBackgroundColor(QColor(Qt.GlobalColor.transparent))
            view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            src = QUrl.fromLocalFile(str(self._path)).toString()
            page = _PAGE.format(
                src=escape(src, quote=True), width=self.width(), height=self.height(), fade_ms=self.FADE_MS
            )
            view.loadFinished.connect(self._on_loaded)
            # base URL = the asset folder, so the page may load the local SVG file
            view.setHtml(page, QUrl.fromLocalFile(str(self._path.parent) + "/"))
        except Exception:  # GPU / sandbox problems: still show the picture
            logger.warning("Qt WebEngine unavailable, using the built-in SVG renderer", exc_info=True)
            return None
        self.uses_web_engine = True
        return view

    # ------------------------------------------------------------------ reveal
    def showEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        if self.uses_web_engine:
            self._reveal_timer.start(self._reveal_delay_ms)

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        if self.uses_web_engine:
            self._reveal_timer.stop()
            self._set_shown(False)  # fade in again next time

    def _on_loaded(self, ok: bool) -> None:
        self._loaded = ok
        if ok and self._want_shown:
            self._apply_shown()

    def _set_shown(self, shown: bool) -> None:
        self._want_shown = shown
        if self._loaded:
            self._apply_shown()

    def _apply_shown(self) -> None:
        action = "add" if self._want_shown else "remove"
        self._view.page().runJavaScript(f"document.querySelector('img').classList.{action}('shown');")

    def _make_svg_widget(self) -> QWidget:
        """Fallback: one still frame drawn by Qt's SVG renderer.

        Not animated on purpose: this SVG takes ~0.25 s per frame to render with QtSvg, which
        would make the whole UI sluggish.
        """
        label = QLabel(self)
        label.setFixedSize(self.size())
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setPixmap(_still_frame(self._path, self.width(), self.height(), max(self.devicePixelRatioF(), 1.0)))
        return label

    @staticmethod
    def _svg_aspect_ratio(path: Path) -> float:
        """height / width from the SVG's viewBox (read from the first bytes only - the file is large)."""
        import re

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                head = handle.read(4096)
        except OSError:
            return 0.75
        match = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', head)
        if not match or float(match.group(1)) == 0:
            return 0.75
        return float(match.group(2)) / float(match.group(1))
