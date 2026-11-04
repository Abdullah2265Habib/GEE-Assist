"""Left half of the sign-in screen: soft earth gradient, orbit lines and the looping Earth GIF."""

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


class HeroPanel(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumWidth(380)

        brand_icon = QLabel()
        brand_icon.setPixmap(round_logo(46, self.devicePixelRatioF()))
        brand_name = QLabel("GEE-Assist")
        brand_name.setStyleSheet(f"font-family: '{theme.SERIF}'; font-size: 17pt; color: {theme.INK};")
        brand = QHBoxLayout()
        brand.setSpacing(12)
        brand.addWidget(brand_icon)
        brand.addWidget(brand_name)
        brand.addStretch(1)

        # the sign-in screen fades in over ~700 ms after the intro; the picture follows it
        self.earth = AnimatedSvg(EARTH_SVG, 460, reveal_delay_ms=550)

        headline = QLabel("Explore our planet,\none question at a time.")
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        headline.setStyleSheet(
            f"font-family: '{theme.SERIF}'; font-size: 25pt; color: {theme.INK}; background: transparent;"
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
        footer.setStyleSheet(f"color: {theme.SUBTLE}; font-size: 9pt; letter-spacing: 0.5px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 36, 48, 30)
        layout.setSpacing(0)
        layout.addLayout(brand)
        layout.addStretch(3)
        layout.addWidget(self.earth, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(26)
        layout.addWidget(headline)
        layout.addSpacing(12)
        layout.addWidget(tagline)
        layout.addSpacing(28)
        layout.addLayout(features_box)
        layout.addStretch(4)
        layout.addWidget(footer)

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

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Mint (land) to sky (ocean) wash.
        base = QLinearGradient(0, 0, w, h)
        base.setColorAt(0.0, QColor("#EEF8F2"))
        base.setColorAt(0.55, QColor("#EAF4F8"))
        base.setColorAt(1.0, QColor("#E2EEF9"))
        p.fillRect(self.rect(), base)

        # Soft glow behind the globe.
        centre = QPointF(w / 2, h * 0.40)
        glow = QRadialGradient(centre, min(w, h) * 0.42)
        glow.setColorAt(0.0, theme.color(theme.WHITE, 235))
        glow.setColorAt(0.6, theme.color(theme.WHITE, 90))
        glow.setColorAt(1.0, theme.color(theme.WHITE, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(centre, min(w, h) * 0.42, min(w, h) * 0.42)

        # Thin orbit lines, like the logo's.
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i, (colour, alpha) in enumerate(((theme.LEAF, 55), (theme.OCEAN, 45), (theme.OCEAN, 28))):
            rx, ry = w * (0.40 + 0.09 * i), h * (0.13 + 0.035 * i)
            p.save()
            p.translate(centre)
            p.rotate(-14 + 9 * i)
            p.setPen(QPen(theme.color(colour, alpha), 1.4))
            p.drawEllipse(QRectF(-rx, -ry, 2 * rx, 2 * ry))
            p.restore()

        # Hairline separating the panel from the form.
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.drawLine(w - 1, 0, w - 1, h)
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
