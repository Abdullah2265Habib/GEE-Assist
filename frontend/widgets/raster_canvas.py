"""Shows a raster preview: mouse-wheel zoom around the pointer, drag to pan, double-click to fit.

Reports the image pixel under the pointer (``hovered``), or that it left the image
(``left_image``), so the viewer can show the values there.
"""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QFrame, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QWidget

from frontend import theme

ZOOM_STEP = 1.25
MAX_ZOOM = 40.0      # times the "fit to window" size
MIN_ZOOM = 0.5


def rgba_to_image(rgba: np.ndarray) -> QImage:
    """A QImage holding its own copy of an (height, width, 4) uint8 array."""
    data = np.ascontiguousarray(rgba, dtype=np.uint8)
    height, width = data.shape[:2]
    return QImage(data.data, width, height, 4 * width, QImage.Format.Format_RGBA8888).copy()


class RasterCanvas(QGraphicsView):
    hovered = pyqtSignal(float, float)   # image pixel (x, y) under the pointer
    left_image = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._item = QGraphicsPixmapItem()
        self._item.setTransformationMode(Qt.TransformationMode.FastTransformation)  # sharp pixels when zoomed
        self._scene.addItem(self._item)
        self.setScene(self._scene)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QColor(theme.FIELD_BG))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMouseTracking(True)
        self._fit_scale = 1.0

    # ------------------------------------------------------------- image
    def set_image(self, image: QImage, keep_view: bool = False) -> None:
        """Show ``image``; with ``keep_view`` the zoom and position stay (e.g. another view of the same file)."""
        same_size = not self._item.pixmap().isNull() and self._item.pixmap().size() == image.size()
        self._item.setPixmap(QPixmap.fromImage(image))
        self._scene.setSceneRect(self._item.boundingRect())
        if not (keep_view and same_size):
            self.fit()

    def clear(self) -> None:
        self._item.setPixmap(QPixmap())

    def has_image(self) -> bool:
        return not self._item.pixmap().isNull()

    def fit(self) -> None:
        """The whole image in view."""
        if not self.has_image():
            return
        self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)
        self._fit_scale = self.transform().m11()

    def zoom(self) -> float:
        """How far in it is zoomed, relative to the whole image in view (1.0)."""
        return self.transform().m11() / self._fit_scale if self._fit_scale else 1.0

    def zoom_by(self, factor: float) -> None:
        target = min(MAX_ZOOM, max(MIN_ZOOM, self.zoom() * factor))
        self.scale(target / self.zoom(), target / self.zoom())

    # ------------------------------------------------------------- mouse
    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if not self.has_image():
            return
        self.zoom_by(ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.fit()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().mouseMoveEvent(event)
        self.report_position(self.mapToScene(event.position().toPoint()))

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().leaveEvent(event)
        self.left_image.emit()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        if self.has_image() and abs(self.zoom() - 1.0) < 1e-6:
            self.fit()  # still showing the whole image: keep it whole

    def report_position(self, point: QPointF) -> None:
        """Emit the image pixel at ``point`` (scene coordinates), or that it is off the image."""
        size = self._item.pixmap().size()
        if self.has_image() and 0 <= point.x() < size.width() and 0 <= point.y() < size.height():
            self.hovered.emit(point.x(), point.y())
        else:
            self.left_image.emit()
