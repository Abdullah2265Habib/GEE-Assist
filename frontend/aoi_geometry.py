"""Turn shapes drawn on the AOI map into GeoJSON polygons GEE can use.

GeoJSON has no circle type, so a circle is approximated by a geodesic polygon.
Pure Python (no Qt) so it can be unit-tested.
"""

from __future__ import annotations

import json
import math
from typing import Any

EARTH_RADIUS_M = 6_371_008.8
CIRCLE_SEGMENTS = 64


def bbox_polygon(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> dict[str, Any]:
    ring = [[min_lon, min_lat], [max_lon, min_lat], [max_lon, max_lat], [min_lon, max_lat], [min_lon, min_lat]]
    return {"type": "Polygon", "coordinates": [ring]}


def circle_polygon(lon: float, lat: float, radius_m: float, segments: int = CIRCLE_SEGMENTS) -> dict[str, Any]:
    """Polygon whose vertices lie ``radius_m`` metres from (lon, lat) on a sphere, counter-clockwise."""
    phi1, lam1 = math.radians(lat), math.radians(lon)
    delta = radius_m / EARTH_RADIUS_M
    ring = []
    for i in range(segments):
        bearing = 2 * math.pi * i / segments
        phi2 = math.asin(
            math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(bearing)
        )
        lam2 = lam1 + math.atan2(
            math.sin(bearing) * math.sin(delta) * math.cos(phi1),
            math.cos(delta) - math.sin(phi1) * math.sin(phi2),
        )
        ring.append([round(math.degrees(lam2), 7), round(math.degrees(phi2), 7)])
    ring.reverse()  # bearings run clockwise; GeoJSON exterior rings are counter-clockwise
    ring.append(list(ring[0]))
    return {"type": "Polygon", "coordinates": [ring]}


def polygon_from_geojson(text: str) -> dict[str, Any]:
    """Accept a Geometry or Feature JSON string from the map and return the bare geometry."""
    data = json.loads(text)
    if data.get("type") == "Feature":
        data = data.get("geometry") or {}
    return {"type": data.get("type"), "coordinates": data.get("coordinates")}


def bbox_of(geometry: dict[str, Any]) -> list[float]:
    coords = geometry["coordinates"]
    polygons = [coords] if geometry["type"] == "Polygon" else coords
    points = [p for poly in polygons for ring in poly for p in ring]
    lons, lats = [p[0] for p in points], [p[1] for p in points]
    return [min(lons), min(lats), max(lons), max(lats)]


def vertex_count(geometry: dict[str, Any]) -> int:
    """Distinct vertices of the outer ring(s) (the closing position is not counted)."""
    coords = geometry["coordinates"]
    polygons = [coords] if geometry["type"] == "Polygon" else coords
    return sum(len(poly[0]) - 1 for poly in polygons if poly)


def format_distance(metres: float) -> str:
    return f"{metres / 1000:.2f} km" if metres >= 1000 else f"{metres:.0f} m"
