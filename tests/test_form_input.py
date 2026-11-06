"""UC-03 Fill Parameter Form and UC-04 Import GeoJSON."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.business.request import RequestService
from backend.business.request.geojson_utils import utm_epsg_for
from backend.config import ANALYSIS_CATEGORIES, AUTO_UTM, DATASETS
from backend.dto import FormDTO
from backend.exceptions import AOIImportError

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[73.0, 31.0], [73.1, 31.0], [73.1, 31.1], [73.0, 31.1], [73.0, 31.0]]],
}


def valid_form(**overrides) -> FormDTO:
    values = dict(
        dataset="sentinel2_sr",
        bands=["B4", "B8"],
        scale=10,
        max_cloud_cover=20,
        aoi=json.dumps(SQUARE),
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 31),
        crs="EPSG:4326",
        output_dir=str(OUTPUT_DIR),
        analysis_type="Vegetation",
        processes=["NDVI"],
    )
    values.update(overrides)
    return FormDTO(**values)


OUTPUT_DIR = Path(__file__).resolve().parent / "_downloads_not_created"


# ---------------------------------------------------------------- validate_form
def test_valid_form_is_accepted_and_kept():
    service = RequestService()
    result = service.validate_form(valid_form())
    assert result.is_valid, result.errors
    kept = service.get_kept_requests()
    assert len(kept) == 1 and kept[0].source == "form"


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"dataset": ""}, "dataset"),                                        # 8a
        ({"aoi": ""}, "aoi"),                                                # 8a
        ({"start_date": None}, "dates"),                                     # 8a
        ({"start_date": date(2024, 5, 1)}, "dates"),                         # 8b start > end
        ({"end_date": date.today() + timedelta(days=1)}, "dates"),           # 8b future
        ({"start_date": date(2015, 1, 1)}, "dates"),                         # before dataset exists
        ({"bands": []}, "bands"),
        ({"bands": ["SR_B4"]}, "bands"),                                     # band of another dataset
        ({"scale": 0}, "scale"),
        ({"max_cloud_cover": 150}, "max_cloud_cover"),
        ({"composite": "sum"}, "composite"),
        ({"crs": "WGS84"}, "crs"),
        ({"crs": ""}, "crs"),
        ({"output_dir": ""}, "output_dir"),
        ({"output_dir": "relative/folder"}, "output_dir"),
        ({"output_dir": __file__}, "output_dir"),                            # a file, not a folder
        ({"analysis_type": "LST", "processes": ["LSTMapping"]}, "analysis_type"),  # 8c
        ({"processes": []}, "processes"),
        ({"processes": ["NDWI"]}, "processes"),
    ],
)
def test_invalid_form_reports_field_and_is_not_kept(overrides, field):
    service = RequestService()
    result = service.validate_form(valid_form(**overrides))
    assert not result.is_valid
    assert field in result.errors
    assert service.get_kept_requests() == []


def test_download_only_needs_no_analysis():
    service = RequestService()
    result = service.validate_form(valid_form(analysis_type="", processes=["NDVI"]))
    assert result.is_valid, result.errors
    kept = service.get_kept_requests()[0]
    assert kept.analysis_type == "" and kept.processes == []   # stray processes are dropped


def test_auto_utm_is_resolved_from_the_aoi():
    service = RequestService()
    assert service.validate_form(valid_form(crs=AUTO_UTM)).is_valid
    assert service.get_kept_requests()[0].crs == "EPSG:32643"            # 73 E, 31 N -> zone 43 N


@pytest.mark.parametrize(
    "lon, lat, expected",
    [(73.05, 31.4, "EPSG:32643"), (-0.1, 51.5, "EPSG:32630"), (151.2, -33.9, "EPSG:32756"), (180.0, 0.0, "EPSG:32660")],
)
def test_utm_zone_lookup(lon, lat, expected):
    point_box = {"type": "Polygon", "coordinates": [[[lon, lat], [lon, lat + 0.01], [lon - 0.01, lat], [lon, lat]]]}
    assert utm_epsg_for(point_box) == expected


def test_end_date_after_discontinued_dataset_rejected():
    form = valid_form(dataset="landsat5_l2", bands=["SR_B3", "SR_B4"], scale=30,
                      start_date=date(2011, 1, 1), end_date=date(2013, 1, 1))
    result = RequestService().validate_form(form)
    assert "dates" in result.errors


def test_sar_dataset_rejects_optical_water_index():
    form = valid_form(dataset="sentinel1_grd", bands=["VV"], max_cloud_cover=None,
                      analysis_type="Water", processes=["NDWI"])
    result = RequestService().validate_form(form)
    assert "processes" in result.errors
    ok = RequestService().validate_form(replace(form, processes=["WaterBodyDetection"]))
    assert ok.is_valid, ok.errors


@pytest.mark.parametrize("key", list(DATASETS))
def test_every_catalogue_dataset_accepts_its_own_defaults(key):
    """Catalogue consistency: defaults + any supported analysis must validate."""
    info = DATASETS[key]
    category, processes = next(iter(info.supported_analyses.items()))
    end = info.max_date or date.today()
    form = valid_form(
        dataset=key,
        bands=list(info.default_bands),
        scale=info.default_scale,
        max_cloud_cover=20 if info.supports_cloud_filter else None,
        composite=info.default_composite,
        start_date=max(info.min_date, end - timedelta(days=90)),
        end_date=end,
        analysis_type=category,
        processes=[processes[0]],
    )
    result = RequestService().validate_form(form)
    assert result.is_valid, result.errors
    assert set(info.default_bands) <= set(info.bands)
    for category, procs in info.supported_analyses.items():
        assert set(procs) <= set(ANALYSIS_CATEGORIES[category])


def test_cloud_filter_rejected_for_dataset_without_it():
    form = valid_form(dataset="modis_lst", bands=["LST_Day_1km"], scale=1000,
                      analysis_type="LST", processes=["LSTMapping"], max_cloud_cover=10)
    result = RequestService().validate_form(form)
    assert "max_cloud_cover" in result.errors


def test_degenerate_bbox_rejected():
    flat = {"type": "Polygon", "coordinates": [[[1, 1], [1, 1], [1, 1], [1, 1]]]}
    result = RequestService().validate_form(valid_form(aoi=json.dumps(flat)))
    assert "aoi" in result.errors


# ------------------------------------------------------------------ import_aoi
def _write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return str(path)


def test_import_polygon_geometry(tmp_path):
    aoi = RequestService().import_aoi(_write(tmp_path, "aoi.geojson", SQUARE))
    assert json.loads(aoi) == SQUARE


def test_import_feature_collection_merges_polygons(tmp_path):
    other = {"type": "Polygon", "coordinates": [[[74, 32], [74.1, 32], [74.1, 32.1], [74, 32]]]}
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": SQUARE},
            {"type": "Feature", "properties": {}, "geometry": other},
        ],
    }
    aoi = json.loads(RequestService().import_aoi(_write(tmp_path, "fc.json", fc)))
    assert aoi["type"] == "MultiPolygon"
    assert len(aoi["coordinates"]) == 2


@pytest.mark.parametrize(
    "name, content",
    [
        ("aoi.txt", SQUARE),                                                  # 6b extension
        ("aoi.geojson", "{not json"),                                         # 6a parse
        ("aoi.geojson", {"type": "Point", "coordinates": [73, 31]}),          # not an area
        ("aoi.geojson", {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}),  # open ring
        ("aoi.geojson", {"type": "Polygon", "coordinates": [[[500, 0], [501, 0], [501, 1], [500, 0]]]}),  # not WGS84
    ],
)
def test_import_rejects_invalid_files(tmp_path, name, content):
    with pytest.raises(AOIImportError):
        RequestService().import_aoi(_write(tmp_path, name, content))
