"""The parameter form's methods gkonsol fills it with (the web map is replaced; no window on screen)."""

import json
import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtCore import pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

from backend.business.facade import IBusinessFacade  # noqa: E402
from backend.business.request import RequestService  # noqa: E402
from backend.config import AUTO_UTM  # noqa: E402
from backend.exceptions import AOIImportError  # noqa: E402
from frontend.views import parameter_form_view  # noqa: E402
from frontend.views.parameter_form_view import AOI_DRAW, AOI_FILE, ParameterFormView  # noqa: E402

SQUARE = {"type": "Polygon", "coordinates": [[[73.0, 31.0], [73.1, 31.0], [73.1, 31.1], [73.0, 31.1], [73.0, 31.0]]]}


class StubMap(QWidget):
    """Stands in for the web map, which cannot start in a headless test run."""

    bbox_drawn = pyqtSignal(float, float, float, float)
    circle_drawn = pyqtSignal(float, float, float)
    polygon_drawn = pyqtSignal(str)
    shape_cleared = pyqtSignal()
    available = True

    def __init__(self, parent=None):
        super().__init__(parent)
        self.calls = []

    def set_mode(self, mode):
        self.calls.append(("mode", mode))

    def set_bbox(self, *bbox, fit=True):
        self.calls.append(("bbox", bbox))

    def set_shape(self, geojson, fit=True):
        self.calls.append(("shape", geojson))

    def clear_shape(self):
        self.calls.append(("clear",))

    def show_geojson(self, geojson):
        self.calls.append(("show", geojson))


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(app, monkeypatch, tmp_path):
    monkeypatch.setattr(parameter_form_view, "AoiMapWidget", StubMap)
    facade = MagicMock(spec=IBusinessFacade)
    service = RequestService()
    facade.submit_form.side_effect = service.validate_form
    facade.import_aoi.side_effect = service.import_aoi
    form = ParameterFormView(facade)
    form.kept = []
    form.request_kept.connect(form.kept.append)
    form.set_output_dir(str(tmp_path))
    yield form
    form.deleteLater()


def test_fields_are_set_as_the_user_would(view):
    view.set_dataset("landsat8_l2")
    view.set_bands(["SR_B5", "SR_B4"])
    view.set_scale(60)
    view.set_cloud_cover(15)
    view.set_composite("mean")
    view.set_dates(date(2024, 6, 1), date(2024, 8, 31))
    view.set_crs(AUTO_UTM)
    view.set_analysis("Vegetation", ["NDVI", "EVI"])
    form = view.collect_form()
    assert (form.dataset, form.scale, form.max_cloud_cover, form.composite) == ("landsat8_l2", 60, 15, "mean")
    assert form.bands == ["SR_B4", "SR_B5"]  # in the dataset's order
    assert (form.start_date, form.end_date, form.crs) == (date(2024, 6, 1), date(2024, 8, 31), AUTO_UTM)
    assert (form.analysis_type, form.processes) == ("Vegetation", ["NDVI", "EVI"])


def test_choosing_the_same_dataset_again_brings_its_defaults_back(view):
    view.set_scale(99)
    view.set_dataset("sentinel2_sr")
    assert view.collect_form().scale == 10


def test_unknown_values_are_refused(view):
    for setter, value in ((view.set_dataset, "nope"), (view.set_crs, "EPSG:1")):
        with pytest.raises(ValueError):
            setter(value)
    with pytest.raises(ValueError):
        view.set_analysis("Astrology", [])


def test_analysis_none_means_download_only(view):
    view.set_analysis("Water", ["NDWI"])
    view.set_analysis("", [])
    assert view.collect_form().analysis_type == "" and view.processes_field.isHidden()


def test_a_drawn_area_switches_to_draw_mode(view):
    view.set_drawn_area(json.dumps(SQUARE), "Rectangle")
    form = view.collect_form()
    assert view.aoi_draw_toggle.isChecked() and view.aoi_summary_stack.currentIndex() == AOI_DRAW
    assert json.loads(form.aoi) == SQUARE and form.aoi_name == "Rectangle"
    assert ("bbox", (73.0, 31.0, 73.1, 31.1)) in view.map_widget.calls


def test_an_imported_area_switches_to_file_mode(view, tmp_path):
    path = tmp_path / "punjab.geojson"
    path.write_text(json.dumps(SQUARE), encoding="utf-8")
    view.aoi_draw_toggle.setChecked(True)
    view.import_geojson(str(path))
    form = view.collect_form()
    assert view.aoi_file_toggle.isChecked() and view.aoi_summary_stack.currentIndex() == AOI_FILE
    assert form.aoi_name == "punjab.geojson" and json.loads(form.aoi) == SQUARE
    assert "punjab.geojson" in view.aoi_file_label.text()


def test_a_bad_file_is_shown_under_the_area_and_raised(view, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not geojson", encoding="utf-8")
    with pytest.raises(AOIImportError):
        view.import_geojson(str(path))
    assert not view._error_labels["aoi"].isHidden() and view.collect_form().aoi == ""


def test_clear_area(view):
    view.set_drawn_area(json.dumps(SQUARE), "Rectangle")
    view.clear_area()
    assert view.collect_form().aoi == "" and ("clear",) in view.map_widget.calls


def test_submit_returns_the_result_and_keeps_valid_forms(view):
    result = view.submit()
    assert not result.is_valid and "aoi" in result.errors and view.kept == []
    assert not view._error_labels["aoi"].isHidden()  # the form shows the error too
    view.set_drawn_area(json.dumps(SQUARE), "Rectangle")
    result = view.submit()
    assert result.is_valid and len(view.kept) == 1 and view.kept[0].aoi_name == "Rectangle"


# ------------------------------------------------------------------ place search
def _place(display: str, kind: str = "city", geometry=SQUARE):
    from backend.dto import PlaceDTO

    return PlaceDTO(display.split(",")[0], display, kind, json.dumps(geometry))


def test_a_found_place_becomes_the_exact_area(view):
    lahore = _place("Lahore, Punjab, Pakistan")
    view.show_places([lahore])
    form = view.collect_form()
    assert view.aoi_draw_toggle.isChecked() and not view.place_box.isHidden()
    assert json.loads(form.aoi) == SQUARE and form.aoi_name == "Lahore"
    assert ("shape", lahore.aoi) in view.map_widget.calls  # the outline itself, not its bounding box
    assert view.place_results_combo.isHidden()  # only one match: nothing to choose


def test_other_matches_can_be_chosen(view):
    district = {"type": "Polygon", "coordinates": [[[74.0, 31.2], [74.8, 31.2], [74.8, 31.9], [74.0, 31.9], [74.0, 31.2]]]}
    view.show_places([_place("Lahore, Punjab, Pakistan"), _place("Lahore District, Punjab, Pakistan", "district", district)])
    assert not view.place_results_combo.isHidden() and view.place_results_combo.count() == 2
    view.place_results_combo.activated.emit(1)
    form = view.collect_form()
    assert form.aoi_name == "Lahore District" and json.loads(form.aoi) == district


def test_place_search_errors_are_shown_under_the_area(view):
    from backend.exceptions import PlaceSearchError

    view._place_search_id = 7
    view._on_place_search_failed(7, PlaceSearchError("No boundary found for \"Atlantis\"."))
    assert "Atlantis" in view._error_labels["aoi"].text() and view.place_search_button.isEnabled()


def test_a_superseded_search_answer_is_ignored(view):
    view._place_search_id = 3
    view._on_places_found(2, [_place("Old, Answer")])
    assert view.collect_form().aoi == ""


def test_an_empty_place_name_asks_for_one(view):
    view.aoi_draw_toggle.click()
    view.place_search_button.click()
    assert not view._error_labels["aoi"].isHidden() and view.place_search_button.isEnabled()
    view._facade.search_place.assert_not_called()


def test_clear_area_forgets_the_place_search(view):
    view.place_edit.setText("Lahore")
    view.show_places([_place("Lahore, Punjab, Pakistan"), _place("Lahore District, Punjab, Pakistan")])
    view.clear_area()
    assert view.collect_form().aoi == "" and view.place_edit.text() == ""
    assert view.place_results_combo.isHidden() and view.place_results_combo.count() == 0
