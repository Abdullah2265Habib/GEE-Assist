"""Shapes drawn on the AOI map -> GeoJSON polygons (rectangle, circle, custom polygon)."""

from __future__ import annotations

import json
import math

import pytest

from backend.business.request.geojson_utils import _ring_area, validate_geometry
from frontend.aoi_geometry import (
    EARTH_RADIUS_M,
    bbox_of,
    bbox_polygon,
    circle_polygon,
    format_distance,
    polygon_from_geojson,
    vertex_count,
)


def _haversine_m(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def test_bbox_polygon_is_valid_aoi():
    geometry = bbox_polygon(73.0, 31.0, 74.0, 32.0)
    assert validate_geometry(geometry) is None
    assert bbox_of(geometry) == [73.0, 31.0, 74.0, 32.0]


@pytest.mark.parametrize("lon, lat, radius", [(74.35, 31.52, 5_000), (0.0, 0.0, 250), (-70.0, 65.0, 120_000)])
def test_circle_vertices_lie_on_the_radius(lon, lat, radius):
    geometry = circle_polygon(lon, lat, radius)
    ring = geometry["coordinates"][0]
    for vlon, vlat in ring:
        assert _haversine_m(lon, lat, vlon, vlat) == pytest.approx(radius, rel=1e-4)


def test_circle_is_a_closed_counter_clockwise_valid_aoi():
    geometry = circle_polygon(74.35, 31.52, 5_000, segments=64)
    ring = geometry["coordinates"][0]
    assert geometry["type"] == "Polygon"
    assert len(ring) == 65 and ring[0] == ring[-1]
    assert _ring_area(ring) > 0  # positive shoelace area = counter-clockwise (GeoJSON right-hand rule)
    assert validate_geometry(geometry) is None
    assert vertex_count(geometry) == 64


def test_circle_extent_matches_radius():
    radius = 10_000
    min_lon, min_lat, max_lon, max_lat = bbox_of(circle_polygon(74.0, 31.0, radius))
    degrees_lat = math.degrees(radius / EARTH_RADIUS_M)
    assert max_lat - 31.0 == pytest.approx(degrees_lat, rel=1e-3)
    assert 31.0 - min_lat == pytest.approx(degrees_lat, rel=1e-3)
    assert max_lon - 74.0 > degrees_lat  # longitude degrees are shorter away from the equator


def test_polygon_from_leaflet_geometry():
    drawn = {"type": "Polygon", "coordinates": [[[73, 31], [74, 31], [74.5, 32], [73.2, 32.4], [73, 31]]]}
    geometry = polygon_from_geojson(json.dumps(drawn))
    assert geometry == drawn
    assert validate_geometry(geometry) is None
    assert vertex_count(geometry) == 4


def test_polygon_from_feature_unwraps_geometry():
    feature = {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}
    assert polygon_from_geojson(json.dumps(feature))["type"] == "Polygon"


@pytest.mark.parametrize("metres, text", [(850, "850 m"), (1_000, "1.00 km"), (12_345, "12.35 km")])
def test_format_distance(metres, text):
    assert format_distance(metres) == text


# ----------------------------------------------------------------------------- download estimate
from frontend.aoi_geometry import estimate_download, format_bytes  # noqa: E402

MB = 1024 * 1024


def test_estimate_small_aoi_fits_in_one_request():
    box = bbox_polygon(73.0, 31.4, 73.05, 31.45)          # ~4.7 x 5.5 km
    est = estimate_download(box, 10, 5, 4, 48 * MB, 32_768)
    assert 450 < est.width_px < 500 and 540 < est.height_px < 570
    assert est.total_bytes == est.width_px * est.height_px * 5 * 4
    assert est.requests == 1


def test_estimate_large_aoi_needs_several_requests():
    box = bbox_polygon(73.0, 31.0, 74.0, 32.0)            # ~95 x 110 km at 10 m, 5 bands -> ~2 GB
    est = estimate_download(box, 10, 5, 4, 48 * MB, 32_768)
    assert est.requests == math.ceil(est.total_bytes / (48 * MB)) > 30


def test_estimate_respects_the_pixel_dimension_limit():
    box = bbox_polygon(60.0, 20.0, 80.0, 21.0)            # very wide, 1 band, 1 byte
    est = estimate_download(box, 10, 1, 1, 10**12, 32_768)
    assert est.width_px > 32_768 and est.requests >= math.ceil(est.width_px / 32_768)


@pytest.mark.parametrize("count, text", [(512, "512 B"), (2048, "2.0 KB"), (5 * MB, "5.0 MB"), (3 * 1024 * MB, "3.0 GB")])
def test_format_bytes(count, text):
    assert format_bytes(count) == text
