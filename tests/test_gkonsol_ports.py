"""gkonsol's form without widgets behaves like the parameter form."""

import json
from datetime import date
from unittest.mock import MagicMock

import pytest

from backend.config import DEFAULT_DOWNLOAD_DIR, get_dataset
from backend.dto import FormDTO
from frontend.gkonsol.ports import Context, MemoryForm, months_before

TODAY = date(2026, 11, 10)
SQUARE = json.dumps({"type": "Polygon", "coordinates": [[[73, 31], [73.1, 31], [73.1, 31.1], [73, 31.1], [73, 31]]]})


@pytest.fixture
def form():
    return MemoryForm(MagicMock(), today=lambda: TODAY)


@pytest.mark.parametrize("day, months, expected", [
    (date(2026, 11, 10), 3, date(2026, 8, 10)),
    (date(2026, 2, 15), 3, date(2025, 11, 15)),
    (date(2026, 5, 31), 3, date(2026, 2, 28)),   # February is shorter
])
def test_months_before(day, months, expected):
    assert months_before(day, months) == expected


def test_starts_like_the_parameter_form(form):
    current = form.current()
    assert current.dataset == "sentinel2_sr" and current.bands == ["B2", "B3", "B4", "B8", "B11"]
    assert current.scale == 10 and current.max_cloud_cover == 20 and current.composite == "median"
    assert (current.start_date, current.end_date) == (date(2026, 8, 10), TODAY)
    assert current.crs == "EPSG:4326" and current.output_dir == str(DEFAULT_DOWNLOAD_DIR)
    assert current.aoi == "" and current.analysis_type == ""


def test_choosing_a_dataset_sets_its_defaults(form):
    form.set_bands(["B4"])
    form.set_dataset("modis_lst")
    current = form.current()
    assert current.bands == list(get_dataset("modis_lst").default_bands)
    assert current.scale == 1000 and current.max_cloud_cover is None  # no cloud filter


def test_dates_are_kept_within_the_dataset(form):
    form.set_dates(date(2000, 1, 1), date(2024, 1, 1))
    form.set_dataset("landsat5_l2")  # 1984-03-16 .. 2012-05-05
    current = form.current()
    assert current.start_date == date(2000, 1, 1) and current.end_date == date(2012, 5, 5)


def test_unsupported_analysis_is_dropped_with_the_dataset(form):
    form.set_analysis("Vegetation", ["NDVI", "EVI"])
    form.set_dataset("modis_vi_16day")  # supports Vegetation: NDVI and EVI only
    assert form.current().processes == ["NDVI", "EVI"]
    form.set_dataset("sentinel1_grd")   # radar: no vegetation analysis
    assert form.current().analysis_type == "" and form.current().processes == []


def test_unknown_dataset_is_refused(form):
    with pytest.raises(ValueError):
        form.set_dataset("nope")


def test_current_is_a_copy(form):
    form.current().bands.append("XX")
    assert "XX" not in form.current().bands


def test_area_and_output_settings(form):
    form.set_area(SQUARE, "Faisalabad")
    form.set_crs("AUTO_UTM")
    form.set_output_dir("D:/GEE")
    current = form.current()
    assert current.aoi == SQUARE and current.aoi_name == "Faisalabad"
    assert current.crs == "AUTO_UTM" and current.output_dir == "D:/GEE"
    form.clear_area()
    assert form.current().aoi == "" and form.current().aoi_name == ""


def test_apply_fills_what_gemini_understood(form):
    filled = form.apply(FormDTO(dataset="landsat8_l2", max_cloud_cover=10, start_date=date(2024, 1, 1),
                                end_date=date(2024, 3, 31), aoi=SQUARE, aoi_name="Lahore",
                                analysis_type="Vegetation", processes=["NDVI"]))
    assert filled == ["dataset", "cloud cover", "dates", "area (Lahore)", "analysis"]
    current = form.current()
    assert current.dataset == "landsat8_l2" and current.max_cloud_cover == 10 and current.processes == ["NDVI"]


def test_apply_leaves_out_what_was_not_understood(form):
    assert form.apply(FormDTO()) == []
    assert form.apply(FormDTO(dataset="sentinel1_grd", analysis_type="LST")) == ["dataset"]


def test_submit_validates_and_keeps_through_the_facade():
    facade = MagicMock()
    form = MemoryForm(facade, today=lambda: TODAY)
    assert form.submit() is facade.submit_form.return_value
    assert facade.submit_form.call_args.args[0].dataset == "sentinel2_sr"


def test_context_knows_whether_the_user_is_an_administrator():
    facade = MagicMock()
    context = Context(facade=facade, out=None, app=None, form=None, panel=None)
    facade.get_current_user.return_value = MagicMock(is_admin=True)
    assert context.is_admin
    facade.get_current_user.return_value = None
    assert not context.is_admin and context.user is None
