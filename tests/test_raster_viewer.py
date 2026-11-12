"""The GeoTIFF viewer page, on a real (small) file (no window on screen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import MagicMock  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
rasterio = pytest.importorskip("rasterio")
from PyQt6.QtWidgets import QApplication  # noqa: E402

from backend.business.facade import BusinessFacade  # noqa: E402
from backend.business.map import MapService  # noqa: E402
from frontend.views import raster_viewer_view as viewer_module  # noqa: E402
from frontend.views.raster_viewer_view import RasterViewerView  # noqa: E402
from tests.test_map_service import NODATA, write_tif  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _run_now(owner, fn, *args, on_success=None, on_error=None):
    """run_task without the thread pool: the tests see the result straight away."""
    try:
        result = fn(*args)
    except Exception as exc:
        if on_error:
            on_error(exc)
    else:
        if on_success:
            on_success(result)


@pytest.fixture
def viewer(app, monkeypatch):
    monkeypatch.setattr(viewer_module, "run_task", _run_now)
    facade = BusinessFacade(MagicMock(), MagicMock(), MagicMock(), map_service=MapService())
    page = RasterViewerView(facade)
    page.resize(1100, 700)
    yield page
    page.deleteLater()


@pytest.fixture
def sentinel(tmp_path):
    shape = (60, 80)
    veg = np.zeros(shape, dtype=bool)
    veg[:, :40] = True
    bands = {"B2": np.where(veg, 400, 900), "B3": np.where(veg, 700, 1200), "B4": np.where(veg, 500, 600),
             "B8": np.where(veg, 3500, 300), "B11": np.full(shape, 1000)}
    folder = tmp_path / "Sentinel-2_73.0400_31.0700_2023-01-01_2023-12-31"
    folder.mkdir()
    return write_tif(folder / f"{folder.name}.tif", {k: v.astype("float32") for k, v in bands.items()})


def test_opens_a_file_in_true_colour_with_its_details(viewer, sentinel):
    viewer.open(str(sentinel))

    assert viewer.title.text() == "Sentinel-2_73.0400_31.0700_2023-01-01_2023-12-31"
    assert viewer.subtitle.text() == "Sentinel-2  ·  2023-01-01 to 2023-12-31  ·  80 × 60 px  ·  5 bands"
    assert viewer.canvas.has_image() and viewer.view.preset.key == "true_colour"
    assert [viewer.preset_box.itemText(i) for i in range(4)] == [
        "True colour", "False colour (vegetation)", "NDVI (vegetation)", "NDWI (water)"]
    assert viewer.detail_labels["bands"].text() == "B2, B3, B4, B8, B11"
    assert viewer.detail_labels["crs"].text() == "EPSG:4326"
    path_label = viewer.detail_labels["path"]   # long paths are shortened to fit; all of it in the tooltip
    assert path_label.full_text() == str(sentinel) and path_label.toolTip() == str(sentinel)
    assert viewer.legend.item_texts() == ["Red ← B4", "Green ← B3", "Blue ← B2"]
    assert viewer.preset_box.isEnabled() and viewer.banner.isHidden()


def test_choosing_another_view_redraws_with_its_legend(viewer, sentinel):
    viewer.open(str(sentinel))
    viewer.preset_box.setCurrentIndex(2)  # NDVI

    assert viewer.view.preset.key == "ndvi" and viewer.legend.title.text() == "NDVI (vegetation)"
    assert "(NIR - Red)" in viewer.preset_note.text()


def test_values_under_the_pointer_with_the_index_there(viewer, sentinel):
    viewer.open(str(sentinel))
    viewer.preset_box.setCurrentIndex(2)  # NDVI
    viewer._on_hovered(10.5, 30.5)        # the vegetation half
    viewer._read_values()                 # (normally after the pointer rests a moment)

    assert viewer.value_labels["B8"].text() == "3,500" and viewer.value_labels["B4"].text() == "500"
    lines = viewer.pointer_label.text().splitlines()
    assert lines[0] == "31.06950°, 73.01050°"
    assert lines[1] == "NDVI: 0.750"       # (3500 - 500) / (3500 + 500)

    viewer._on_left_image()
    assert viewer.value_labels["B8"].text() == "–"


def test_land_cover_class_is_named_under_the_pointer(viewer, tmp_path):
    labels = np.full((10, 10), 6, dtype="float32")  # built area
    folder = tmp_path / "Dynamic-World_73.0000_31.0000_2023-01-01_2023-12-31"
    folder.mkdir()
    viewer.open(str(write_tif(folder / f"{folder.name}.tif", {"label": labels})))
    viewer._on_hovered(5, 5)
    viewer._read_values()

    assert viewer.view.preset.key == "classes"
    assert viewer.pointer_label.text().splitlines()[1] == "Built area"


def test_a_file_that_cannot_be_read_shows_an_error(viewer, tmp_path):
    broken = tmp_path / "broken.tif"
    broken.write_text("not a raster")
    viewer.open(str(broken))

    assert not viewer.banner.isHidden() and "not a GeoTIFF" in viewer.banner.text()
    assert not viewer.preset_box.isEnabled() and not viewer.canvas.has_image()


def test_large_files_say_they_are_shown_scaled_down(viewer, sentinel, monkeypatch):
    monkeypatch.setattr(viewer._facade, "render_raster",
                        lambda info, preset, max_size=1600: MapService().render(info, preset, max_size=20))
    viewer.open(str(sentinel))
    assert viewer.banner.text() == "Shown at 1/4.0 of full resolution."


# ------------------------------------------------------------------ show on the map
def test_show_on_map_sends_the_current_view_where_the_file_lies(viewer, sentinel):
    from PyQt6.QtGui import QImage

    assert not viewer.map_button.isEnabled()   # nothing drawn yet
    viewer.open(str(sentinel))
    viewer.preset_box.setCurrentIndex(2)      # NDVI
    sent = []
    viewer.show_on_map_requested.connect(lambda png, bounds, title: sent.append((png, bounds, title)))

    assert viewer.map_button.isEnabled()
    viewer.map_button.click()

    [(png, bounds, title)] = sent
    image = QImage.fromData(png, "PNG")
    assert png.startswith(b"\x89PNG") and (image.width(), image.height()) == (80, 60)
    assert bounds == viewer.info.bounds
    assert title == "Sentinel-2_73.0400_31.0700_2023-01-01_2023-12-31 · NDVI (vegetation)"


def test_pictures_for_the_map_are_kept_small(viewer, sentinel):
    from PyQt6.QtGui import QImage

    viewer.open(str(sentinel))
    image = QImage.fromData(viewer.map_png(max_size=40), "PNG")
    assert (image.width(), image.height()) == (40, 30)
