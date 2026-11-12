"""The zoomable raster canvas (no window on screen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from frontend.widgets.raster_canvas import MAX_ZOOM, RasterCanvas, rgba_to_image  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def canvas(app):
    view = RasterCanvas()
    view.resize(400, 300)
    view.show()
    rgba = np.zeros((100, 200, 4), dtype=np.uint8)
    rgba[..., 0] = 200
    rgba[..., 3] = 255
    view.set_image(rgba_to_image(rgba))
    yield view
    view.deleteLater()


def test_rgba_array_becomes_an_image_with_its_own_copy(app):
    rgba = np.zeros((3, 5, 4), dtype=np.uint8)
    rgba[1, 2] = (10, 20, 30, 255)
    image = rgba_to_image(rgba)
    rgba[1, 2] = 0  # changing the array afterwards does not change the image
    assert (image.width(), image.height()) == (5, 3)
    colour = image.pixelColor(2, 1)
    assert (colour.red(), colour.green(), colour.blue(), colour.alpha()) == (10, 20, 30, 255)


def test_starts_with_the_whole_image_in_view(canvas):
    assert canvas.zoom() == pytest.approx(1.0)
    visible = canvas.mapToScene(canvas.viewport().rect()).boundingRect()
    assert visible.width() >= 199 and visible.height() >= 99


def test_zooms_in_and_out_within_limits_and_fits_again(canvas):
    canvas.zoom_by(2.0)
    assert canvas.zoom() == pytest.approx(2.0)
    canvas.zoom_by(1000)
    assert canvas.zoom() == pytest.approx(MAX_ZOOM)
    canvas.fit()
    assert canvas.zoom() == pytest.approx(1.0)


def test_reports_the_pixel_under_the_pointer_or_leaving_the_image(canvas):
    seen = []
    canvas.hovered.connect(lambda x, y: seen.append((round(x), round(y))))
    canvas.left_image.connect(lambda: seen.append("left"))

    canvas.report_position(QPointF(150.2, 40.7))
    canvas.report_position(QPointF(250, 40))       # past the right edge
    assert seen == [(150, 41), "left"]


def test_another_view_of_the_same_file_keeps_the_zoom(canvas):
    canvas.zoom_by(3.0)
    same_size = np.zeros((100, 200, 4), dtype=np.uint8)
    canvas.set_image(rgba_to_image(same_size), keep_view=True)
    assert canvas.zoom() == pytest.approx(3.0)
    canvas.set_image(rgba_to_image(np.zeros((50, 50, 4), dtype=np.uint8)), keep_view=True)  # another file
    assert canvas.zoom() == pytest.approx(1.0)
