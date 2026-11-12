"""The raster legend (no window on screen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication  # noqa: E402

from backend.dto.map_dto import LegendDTO  # noqa: E402
from frontend.widgets.raster_legend import ColourBar, RasterLegend, format_value  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def legend(app):
    widget = RasterLegend()
    yield widget
    widget.deleteLater()


@pytest.mark.parametrize("value, text", [
    (None, "no data"), (0.4237, "0.424"), (-0.2, "-0.200"), (3.14159, "3.14"), (1530.4, "1,530"),
    (47506.8, "47,507"), (12.0, "12"), (0.0000452, "4.5e-05"),
])
def test_values_read_briefly(value, text):
    assert format_value(value) == text


def test_scale_shows_a_colour_bar_and_its_range(legend):
    legend.set_legend(LegendDTO("scale", "NDVI (vegetation)", low=-0.2, high=0.8, colours=("#A50026", "#1A7837")))
    assert legend.title.text() == "NDVI (vegetation)"
    assert legend.findChildren(ColourBar)[0].colours == ("#A50026", "#1A7837")
    assert legend.item_texts() == ["-0.200", "0.800"]


def test_classes_list_each_class(legend):
    legend.set_legend(LegendDTO("classes", "Land cover classes", colours=("#419BDF", "#C4281B"),
                                labels=("Water", "Built area")))
    assert legend.item_texts() == ["Water", "Built area"]
    assert not legend.findChildren(ColourBar)


def test_colour_composites_show_which_band_is_which_colour(legend):
    legend.set_legend(LegendDTO("rgb", "True colour", labels=("B4", "B3", "B2")))
    assert legend.item_texts() == ["Red ← B4", "Green ← B3", "Blue ← B2"]


def test_a_new_legend_replaces_the_old_one(legend):
    legend.set_legend(LegendDTO("classes", "Land cover classes", colours=("#419BDF",), labels=("Water",)))
    legend.set_legend(LegendDTO("rgb", "False colour (vegetation)", labels=("B8", "B4", "B3")))
    assert legend.item_texts() == ["Red ← B8", "Green ← B4", "Blue ← B3"]
