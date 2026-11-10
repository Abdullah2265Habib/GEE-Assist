"""gkonsol's parameter form commands: form show / set / aoi / validate / estimate / wizard / submit, and ask."""

import json
from datetime import date, timedelta

import pytest

from backend.business.request import RequestService
from backend.config import AUTO_UTM
from backend.dto import EntityDTO, FormDTO
from tests.gkonsol_fakes import terminal

SQUARE = {"type": "Polygon", "coordinates": [[[73.0, 31.0], [73.1, 31.0], [73.1, 31.1], [73.0, 31.1], [73.0, 31.0]]]}


@pytest.fixture
def term(tmp_path):
    term = terminal()
    service = RequestService()  # real validation, keeping and GeoJSON import
    term.facade.check_form.side_effect = service.check_form
    term.facade.submit_form.side_effect = service.validate_form
    term.facade.get_kept_requests.side_effect = service.get_kept_requests
    term.facade.import_aoi.side_effect = service.import_aoi
    term.form.set_output_dir(str(tmp_path / "downloads"))
    return term


def _current(term) -> FormDTO:
    return term.form.current()


# ------------------------------------------------------------------ show
def test_form_show_lists_every_field(term):
    printed = term.type("form")
    for label in ("Dataset", "Bands", "Scale", "Cloud cover", "Composite", "Area", "Dates", "Projection",
                  "Save to", "Analysis"):
        assert label in printed
    assert "sentinel2_sr  (Sentinel-2 Surface Reflectance (L2A))" in printed
    assert "not chosen: form aoi bbox | circle | file" in printed and "none (download only)" in printed


def test_form_show_json(term):
    term.type("form aoi bbox 73 31 73.1 31.1")
    data = json.loads(term.type("form show --json").split("\n", 1)[1])
    assert data["dataset"] == "sentinel2_sr" and data["aoi"]["type"] == "Polygon"


# ------------------------------------------------------------------ set
def test_set_dataset_uses_its_defaults(term):
    printed = term.type("form set dataset landsat-8")
    assert "✓ dataset = landsat8_l2 (Landsat 8 Collection 2 Level-2)" in printed
    current = _current(term)
    assert current.dataset == "landsat8_l2" and current.scale == 30 and current.bands[0] == "SR_B2"


def test_set_bands(term):
    assert "bands = B4, B8" in term.type("form set bands b4,B8 b4")
    assert _current(term).bands == ["B4", "B8"]
    term.type("form set bands all")
    assert len(_current(term).bands) == 14
    term.type("form set bands default")
    assert _current(term).bands == ["B2", "B3", "B4", "B8", "B11"]
    printed = term.type("form set bands B4 SR_B5")
    assert "has no band SR_B5" in printed and "Its bands: B1 B2" in printed


def test_set_scale_cloud_and_composite(term):
    term.type("form set scale 30m")
    term.type("form set cloud 15%")
    term.type("form set composite MEAN")
    current = _current(term)
    assert (current.scale, current.max_cloud_cover, current.composite) == (30, 15, "mean")
    assert "from 1 to 100000" in term.type("form set scale 0")
    assert "from 0 to 100" in term.type("form set cloud 101")
    assert "one of: median, mean" in term.type("form set composite sum")
    term.type("form set dataset sentinel1_grd")
    assert "has no cloud-cover filter" in term.type("form set cloud 10")


def test_set_dates(term):
    assert "dates = 2024-06-01 → 2024-08-31" in term.type("form set dates 2024-06-01 2024-08-31")
    term.type("form set start 2024-05-01")
    term.type("form set end 2024-09-30")
    current = _current(term)
    assert (current.start_date, current.end_date) == (date(2024, 5, 1), date(2024, 9, 30))


@pytest.mark.parametrize("line, message", [
    ("form set dates 2024-08-31 2024-06-01", "start date must be on or before the end date"),
    (f"form set dates 2024-01-01 {(date.today() + timedelta(days=2)).isoformat()}", "cannot be in the future"),
    ("form set dates 2015-01-01 2016-01-01", "starts on 2017-03-28"),
    ("form set dates 2024-01-01", "takes two dates"),
    ("form set start 06/01/2024", "YYYY-MM-DD"),
])
def test_bad_dates_are_explained(term, line, message):
    assert message in term.type(line)


def test_set_projection(term):
    term.type("form set crs utm")
    assert _current(term).crs == AUTO_UTM
    term.type("form set projection mercator")
    assert _current(term).crs == "EPSG:3857"
    assert "EPSG:4326 (WGS 84)" in term.type("form set crs EPSG:32643")


def test_set_output_folder_with_spaces(term, tmp_path):
    folder = tmp_path / "GEE data"
    assert "save to" in term.type(f'form set output "{folder}"')
    assert _current(term).output_dir == str(folder)
    term.type(f"form set folder {folder}")  # no quotes: the words are joined
    assert _current(term).output_dir == str(folder)
    assert "full folder path" in term.type("form set output relative\\folder")
    file = tmp_path / "file.txt"
    file.write_text("x")
    assert "is a file, not a folder" in term.type(f'form set output "{file}"')


def test_set_analysis_and_processes(term):
    assert "analysis = Vegetation: NDVI, EVI" in term.type("form set analysis vegetation ndvi,EVI")
    term.type("form set processes SAVI")
    assert _current(term).processes == ["SAVI"]
    assert "does not support LST analysis" in term.type("form set analysis LST LSTMapping")
    assert "has no process LST" in term.type("form set processes LST")
    term.type("form set analysis none")
    assert _current(term).analysis_type == "" and _current(term).processes == []
    assert "Choose the analysis first" in term.type("form set processes NDVI")


def test_set_analysis_without_processes_asks_for_them(term):
    assert "Now choose its processes: form set processes NDWI MNDWI" in term.type("form set analysis Water")


def test_set_an_unknown_field(term):
    assert "The form has no field 'colour'" in term.type("form set colour red")


@pytest.mark.parametrize("typed, expected", [
    ("form set ", ["dataset", "bands", "scale", "cloud", "composite", "dates", "start", "end", "crs", "output",
                   "analysis", "processes"]),
    ("form set dataset landsat8", ["landsat8_l2"]),
    ("form set bands B1", ["B1", "B11", "B12"]),
    ("form set composite m", ["median", "mean", "mosaic", "min", "max", "mode"]),
    ("form set analysis ", ["none", "Water", "Vegetation"]),
    ("form set analysis Vegetation N", ["NDVI"]),
])
def test_set_completes_fields_and_values(term, typed, expected):
    assert term.shell.complete(typed)[1] == expected


# ------------------------------------------------------------------ area
def test_bbox_with_negative_coordinates(term):
    printed = term.type("form aoi bbox -74.05 40.68 -73.90 40.82")
    assert "area = Rectangle (Polygon, 4 vertices) · lon -74.0500 → -73.9000, lat 40.6800 → 40.8200" in printed
    assert "≈" in printed and "chunk" in printed


@pytest.mark.parametrize("line, message", [
    ("form aoi bbox 74 31 73 32", "West must be less than east"),
    ("form aoi bbox 74 91 75 92", "South must be from -90 to 90"),
    ("form aoi bbox 1 2 3", "needs more arguments"),
    ("form aoi circle 73 31 far", "distance such as 500m"),
    ("form aoi circle 73 31 900km", "at most 500 km"),
])
def test_bad_areas_are_explained(term, line, message):
    assert message in term.type(line)


def test_circle(term):
    assert "Circle (r = 10.00 km) (Polygon, 64 vertices)" in term.type("form aoi circle 73.08 31.42 10km")


def test_geojson_file_and_text(term, tmp_path):
    path = tmp_path / "my area.geojson"
    path.write_text(json.dumps(SQUARE), encoding="utf-8")
    assert "area = my area.geojson (Polygon" in term.type(f'form aoi file "{path}"')
    assert "area = GeoJSON from gkonsol" in term.type("form aoi geojson " + json.dumps(SQUARE))
    assert "must be a Polygon" in term.type('form aoi geojson {"type":"Point","coordinates":[1,2]}')
    assert "not GeoJSON" in term.type("form aoi geojson {oops")


def test_unreadable_files_are_reported(term, tmp_path):
    assert "✗" in term.type(f'form aoi file "{tmp_path / "missing.geojson"}"')


def test_area_show_and_clear(term):
    assert "No area chosen" in term.type("form aoi")
    term.type("form aoi bbox 73 31 73.1 31.1")
    assert "Rectangle" in term.type("form area show")
    term.type("form aoi clear")
    assert _current(term).aoi == ""


# ------------------------------------------------------------------ validate, estimate, submit, reset
def test_validate_lists_what_to_fix(term):
    printed = term.type("form validate")
    assert "✗ Area: Specify an Area of Interest" in printed and "→ form aoi bbox" in printed
    term.type("form aoi bbox 73 31 73.1 31.1")
    assert "✓ All parameters are valid." in term.type("form check")
    assert term.facade.get_kept_requests() == []  # nothing kept


def test_estimate(term):
    assert "needs an area" in term.type("form estimate")
    term.type("form aoi bbox 73 31 73.1 31.1")
    printed = term.type("form estimate")
    assert "× " in printed and "float32" in printed and "chunk" in printed and "GEE requests" in printed


def test_submit_keeps_the_request(term):
    printed = term.type("form submit")
    assert "Area: Specify an Area of Interest" in printed
    term.type("form aoi bbox 73 31 73.1 31.1")
    printed = term.type("form submit")
    assert "✓ Parameters accepted and kept as request #1." in printed and "download start 1" in printed


def test_reset_asks_first(term):
    term.type("form set scale 99")
    term.type("form reset")
    term.type("n")
    assert _current(term).scale == 99
    term.type("form reset -y")
    assert _current(term).scale == 10


# ------------------------------------------------------------------ wizard
def test_wizard_asks_for_each_field_and_submits(term, tmp_path):
    term.type("form wizard")
    answers = [
        "landsat8_l2",              # dataset
        "",                         # bands: keep
        "60",                       # scale
        "abc", "15",                # cloud: wrong, then right
        "",                         # composite
        "2024-06-01", "2024-08-31",
        "bbox 73 31 73.1 31.1",     # area
        "utm",                      # projection
        "",                         # folder
        "Vegetation NDVI",          # analysis
        "y",                        # submit
    ]
    for answer in answers:
        assert term.shell.runner.asking is not None, term.output()
        term.type(answer)
    printed = term.output()
    assert "must be a whole number" in printed  # the wrong answer, asked again
    assert "kept as request #1" in printed and term.shell.running is None
    kept = term.facade.get_kept_requests()[0]
    assert (kept.dataset, kept.scale, kept.max_cloud_cover, kept.analysis_type) == ("landsat8_l2", 60, 15, "Vegetation")


def test_wizard_skips_cloud_for_radar_and_can_be_stopped(term):
    term.type("form fill")
    term.type("sentinel1_grd")
    term.type("")   # bands
    term.type("")   # scale
    assert term.shell.runner.asking.prompt.startswith("Composite")  # no cloud question
    term.type("q")
    assert "Stopped." in term.output() and term.shell.running is None
    assert _current(term).dataset == "sentinel1_grd"


# ------------------------------------------------------------------ ask
def test_ask_fills_the_form_from_gemini(term):
    term.facade.submit_query.return_value = FormDTO(
        dataset="landsat8_l2", start_date=date(2024, 6, 1), end_date=date(2024, 8, 31),
        aoi=json.dumps(SQUARE), aoi_name="Faisalabad", analysis_type="Vegetation", processes=["NDVI"],
        source="nl", notes=["Cloud cover was not mentioned."],
        entities=[EntityDTO("PLACE", "Faisalabad"), EntityDTO("PROCESS", "NDVI")],
    )
    printed = term.type("ask what's the NDVI of Faisalabad in summer 2024 from landsat 8")
    term.facade.submit_query.assert_called_once_with("what's the NDVI of Faisalabad in summer 2024 from landsat 8")
    assert "Recognised: Faisalabad · NDVI" in printed
    assert "✓ Filled: dataset, dates, area (Faisalabad), analysis." in printed
    assert "Cloud cover was not mentioned." in printed and "form submit" in printed
    assert _current(term).dataset == "landsat8_l2"


def test_ask_when_nothing_was_understood(term):
    term.facade.submit_query.return_value = FormDTO(source="nl", clarification="Which place do you mean?")
    assert "! Which place do you mean?" in term.type("gemini something vague")


def test_ask_needs_text(term):
    assert "Describe the data you need" in term.type("ask")
