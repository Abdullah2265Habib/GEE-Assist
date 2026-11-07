"""Right side of the sign-in screen: soft earth gradient with the app description, and the small
animated Earth in the bottom-right corner."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend import theme
from frontend.assets import APP_ICON, EARTH_SVG
from frontend.widgets.animated_svg import AnimatedSvg

_FEATURES = (
    "Ask in plain language, get satellite analysis",
    "Vegetation, water, land cover and surface temperature",
    "Maps, explanations and downloadable reports",
)

EARTH_WIDTH = 210          # small animation in the corner
EARTH_MARGIN = 18          # distance from the panel's right / bottom edges


def brand_row() -> QHBoxLayout:
    """App logo + name, shown in the top-left corner of the sign-in screen."""
    icon = QLabel()
    icon.setPixmap(round_logo(46, 2.0))
    name = QLabel("GEE-Assist")
    name.setStyleSheet(f"font-family: '{theme.SERIF}'; font-size: 17pt; color: {theme.INK}; background: transparent;")
    row = QHBoxLayout()
    row.setSpacing(12)
    row.addWidget(icon)
    row.addWidget(name)
    row.addStretch(1)
    return row


class HeroPanel(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumWidth(420)  # the feature lines stay on one line

        headline = QLabel("Explore our planet,\none question at a time.")
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        headline.setWordWrap(True)
        headline.setStyleSheet(
            f"font-family: '{theme.SERIF}'; font-size: 24pt; color: {theme.INK}; background: transparent;"
        )
        tagline = QLabel("Your conversational gateway to Google Earth Engine.")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setWordWrap(True)
        tagline.setStyleSheet(f"font-size: 11.5pt; color: {theme.MUTED}; background: transparent;")

        features = QVBoxLayout()
        features.setSpacing(10)
        for text in _FEATURES:
            features.addLayout(self._feature(text))
        features_box = QHBoxLayout()
        features_box.addStretch(1)
        features_box.addLayout(features)
        features_box.addStretch(1)

        footer = QLabel("Powered by Google Earth Engine")
        footer.setStyleSheet(f"color: {theme.SUBTLE}; font-size: 9pt; letter-spacing: 0.5px; background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 36, 40, 30)
        layout.setSpacing(0)
        layout.addStretch(1)
        layout.addWidget(headline)
        layout.addSpacing(12)
        layout.addWidget(tagline)
        layout.addSpacing(28)
        layout.addLayout(features_box)
        layout.addStretch(1)
        layout.addWidget(footer)

        # Not part of the layout: pinned to the bottom-right corner in resizeEvent.
        # The sign-in screen fades in over ~700 ms after the intro; the picture follows it.
        self.earth = AnimatedSvg(EARTH_SVG, EARTH_WIDTH, reveal_delay_ms=550, parent=self)
        self.earth.raise_()

    @staticmethod
    def _feature(text: str) -> QHBoxLayout:
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(
            "border-radius: 5px; background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {theme.LEAF}, stop:1 {theme.OCEAN});"
        )
        label = QLabel(text)
        label.setStyleSheet(f"color: {theme.TEXT}; font-size: 10.5pt; background: transparent;")
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(label)
        return row

    def _earth_rect(self) -> QRectF:
        e = self.earth
        return QRectF(self.width() - e.width() - EARTH_MARGIN, self.height() - e.height() - EARTH_MARGIN,
                      e.width(), e.height())

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self.earth.move(self._earth_rect().topLeft().toPoint())

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Mint (land) to sky (ocean) wash.
        base = QLinearGradient(0, 0, w, h)
        base.setColorAt(0.0, QColor(theme.HERO_TOP))
        base.setColorAt(0.55, QColor(theme.HERO_MIDDLE))
        base.setColorAt(1.0, QColor(theme.HERO_BOTTOM))
        p.fillRect(self.rect(), base)

        # Soft glow behind the text.
        centre = QPointF(w / 2, h * 0.46)
        radius = min(w, h) * 0.48
        glow = QRadialGradient(centre, radius)
        glow.setColorAt(0.0, theme.color(theme.WHITE, 220))
        glow.setColorAt(0.6, theme.color(theme.WHITE, 80))
        glow.setColorAt(1.0, theme.color(theme.WHITE, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(centre, radius, radius)

        # Thin orbit lines circling the Earth in the corner, like the logo's.
        earth_centre = self._earth_rect().center()
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i, (colour, alpha) in enumerate(((theme.LEAF, 60), (theme.OCEAN, 45), (theme.OCEAN, 26))):
            rx, ry = EARTH_WIDTH * (0.75 + 0.45 * i), EARTH_WIDTH * (0.30 + 0.16 * i)
            p.save()
            p.translate(earth_centre)
            p.rotate(-18 + 7 * i)
            p.setPen(QPen(theme.color(colour, alpha), 1.3))
            p.drawEllipse(QRectF(-rx, -ry, 2 * rx, 2 * ry))
            p.restore()

        # Hairline separating the panel from the form.
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.drawLine(0, 0, 0, h)
        p.end()


def round_logo(size: int, ratio: float = 2.0) -> QPixmap:
    """The app icon cropped to its circle (the PNG has a white square background)."""
    source = QPixmap(str(APP_ICON))
    scale = max(ratio, 1.0)
    px = round(size * scale)
    result = QPixmap(px, px)
    result.fill(Qt.GlobalColor.transparent)
    if source.isNull():
        return result
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    clip = QPainterPath()
    inset = px * 0.035  # the logo's circle sits slightly inside the square image
    clip.addEllipse(QRectF(inset, inset, px - 2 * inset, px - 2 * inset))
    painter.setClipPath(clip)
    painter.drawPixmap(result.rect(), source)
    painter.end()
    result.setDevicePixelRatio(scale)
    return result
