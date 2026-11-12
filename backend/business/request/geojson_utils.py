"""GeoJSON reading and validation for the Area of Interest (UC-04).

Only polygonal AOIs are accepted (Polygon / MultiPolygon), because GEE needs
an area to clip and download. A FeatureCollection with several polygons is
merged into one MultiPolygon.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.exceptions import AOIImportError

SUPPORTED_EXTENSIONS = (".geojson", ".json")
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
POLYGON_TYPES = ("Polygon", "MultiPolygon")


def read_aoi_geometry(file_path: str) -> dict[str, Any]:
    """Read a GeoJSON file and return a single validated polygonal geometry."""
    path = Path(file_path)

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:                      # 6b
        raise AOIImportError("Unsupported file type. Please select a .geojson or .json file.")
    if not path.is_file():
        raise AOIImportError(f"File not found: {path}")
    if path.stat().st_size > MAX_FILE_SIZE_BYTES:
        raise AOIImportError("The GeoJSON file is too large (limit is 20 MB).")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:                # 6a
        raise AOIImportError("The file is not valid GeoJSON (could not parse JSON).") from exc

    geometry = extract_geometry(data)
    error = validate_geometry(geometry)
    if error:
        raise AOIImportError(error)
    return geometry


def extract_geometry(data: Any) -> dict[str, Any]:
    """Return one Polygon/MultiPolygon from a Geometry, Feature or FeatureCollection."""
    if not isinstance(data, dict) or "type" not in data:
        raise AOIImportError("The file is not a GeoJSON object.")

    gtype = data["type"]
    if gtype == "FeatureCollection":
        geometries = [f.get("geometry") for f in data.get("features") or [] if isinstance(f, dict)]
    elif gtype == "Feature":
        geometries = [data.get("geometry")]
    else:
        geometries = [data]

    polygons = [g for g in geometries if isinstance(g, dict) and g.get("type") in POLYGON_TYPES]
    if not polygons:
        raise AOIImportError("The file contains no Polygon or MultiPolygon boundary to use as an AOI.")
    if len(polygons) == 1:
        return {"type": polygons[0]["type"], "coordinates": polygons[0].get("coordinates")}

    merged: list = []
    for poly in polygons:
        if poly["type"] == "Polygon":
            merged.append(poly.get("coordinates"))
        else:
            merged.extend(poly.get("coordinates") or [])
    return {"type": "MultiPolygon", "coordinates": merged}


def validate_geometry(geometry: Any) -> str | None:
    """Return an error message, or None when the geometry is a usable AOI."""
    if not isinstance(geometry, dict) or geometry.get("type") not in POLYGON_TYPES:
        return "AOI must be a Polygon or MultiPolygon."

    coords = geometry.get("coordinates")
    polygons = [coords] if geometry["type"] == "Polygon" else coords
    if not isinstance(polygons, list) or not polygons:
        return "AOI has no coordinates."

    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            return "AOI contains an empty polygon."
        for i, ring in enumerate(polygon):
            error = _validate_ring(ring)
            if error:
                return error
            if i == 0 and abs(_ring_area(ring)) == 0:
                return "AOI polygon has no area."
    return None


def geometry_bbox(geometry: dict[str, Any]) -> list[float]:
    """[min_lon, min_lat, max_lon, max_lat] of a validated geometry."""
    coords = geometry["coordinates"]
    polygons = [coords] if geometry["type"] == "Polygon" else coords
    lons = [p[0] for poly in polygons for ring in poly for p in ring]
    lats = [p[1] for poly in polygons for ring in poly for p in ring]
    return [min(lons), min(lats), max(lons), max(lats)]


def utm_epsg_for(geometry: dict[str, Any]) -> str:
    """EPSG code of the WGS 84 UTM zone containing the centre of the geometry's extent.

    e.g. Faisalabad (73.1 E, 31.4 N) -> zone 43 North -> "EPSG:32643".
    """
    min_lon, min_lat, max_lon, max_lat = geometry_bbox(geometry)
    lon, lat = (min_lon + max_lon) / 2, (min_lat + max_lat) / 2
    zone = min(int((lon + 180) // 6) + 1, 60)
    return f"EPSG:{32600 + zone if lat >= 0 else 32700 + zone}"


def _validate_ring(ring: Any) -> str | None:
    if not isinstance(ring, list) or len(ring) < 4:
        return "Each polygon ring needs at least 4 positions."
    for position in ring:
        if (
            not isinstance(position, (list, tuple))
            or len(position) < 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in position[:2])
        ):
            return "AOI contains an invalid coordinate."
        lon, lat = position[0], position[1]
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            return "AOI coordinates must be WGS84 longitude/latitude (EPSG:4326)."
    if list(ring[0][:2]) != list(ring[-1][:2]):
        return "Polygon rings must be closed (first and last positions equal)."
    return None


def _ring_area(ring: list) -> float:
    """Shoelace area in degrees² (only used to reject degenerate polygons)."""
    return 0.5 * sum(
        ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)
    )


# ----------------------------------------------------------------------------- simplification
def count_vertices(geometry: dict[str, Any]) -> int:
    """Positions in all rings (the closing position of each ring is not counted)."""
    coords = geometry["coordinates"]
    polygons = [coords] if geometry["type"] == "Polygon" else coords
    return sum(len(ring) - 1 for poly in polygons for ring in poly)


def simplify_geometry(geometry: dict[str, Any], max_vertices: int) -> dict[str, Any]:
    """Return ``geometry`` with at most ``max_vertices`` vertices (Douglas-Peucker).

    The tolerance starts tiny and doubles until the outline fits, so the shape is
    kept as exact as the budget allows. Holes and islands that shrink below the
    tolerance are dropped; the largest polygon is always kept.
    """
    if count_vertices(geometry) <= max_vertices:
        return geometry
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    polygons = sorted(polygons, key=lambda poly: abs(_ring_area(poly[0])), reverse=True)
    min_lon, min_lat, max_lon, max_lat = geometry_bbox(geometry)
    tolerance = max(max_lon - min_lon, max_lat - min_lat) / 100_000

    while True:
        simplified = _simplify_polygons(polygons, tolerance)
        result = (
            {"type": "Polygon", "coordinates": simplified[0]}
            if len(simplified) == 1
            else {"type": "MultiPolygon", "coordinates": simplified}
        )
        if count_vertices(result) <= max_vertices:
            return result
        tolerance *= 2


def _simplify_polygons(polygons: list, tolerance: float) -> list:
    kept = []
    for index, polygon in enumerate(polygons):
        outer = _simplify_ring(polygon[0], tolerance)
        if outer is None:
            if index > 0:
                continue  # an island smaller than the tolerance
            outer = _bbox_ring(polygon[0])  # never lose the main area
        holes = [hole for hole in (_simplify_ring(ring, tolerance) for ring in polygon[1:]) if hole]
        kept.append([outer, *holes])
    return kept


def _simplify_ring(ring: list, tolerance: float) -> list | None:
    """Douglas-Peucker on a closed ring; None when fewer than 3 distinct points remain."""
    # Split the ring at the point farthest from its start, so neither half is degenerate.
    start = ring[0]
    far = max(range(len(ring)), key=lambda i: (ring[i][0] - start[0]) ** 2 + (ring[i][1] - start[1]) ** 2)
    if far == 0:
        return None
    first = _douglas_peucker(ring[: far + 1], tolerance)
    second = _douglas_peucker(ring[far:], tolerance)
    simplified = first + second[1:]
    if len(simplified) < 4:
        return None
    return simplified


def _douglas_peucker(points: list, tolerance: float) -> list:
    """Iterative Douglas-Peucker (country outlines can have too many points for recursion)."""
    n = len(points)
    if n < 3:
        return list(points)
    keep = [False] * n
    keep[0] = keep[-1] = True
    limit = tolerance * tolerance
    stack = [(0, n - 1)]
    while stack:
        first, last = stack.pop()
        ax, ay = points[first][0], points[first][1]
        dx, dy = points[last][0] - ax, points[last][1] - ay
        length = dx * dx + dy * dy
        worst, worst_index = -1.0, -1
        for i in range(first + 1, last):
            px, py = points[i][0] - ax, points[i][1] - ay
            if length == 0:
                distance = px * px + py * py
            else:
                t = max(0.0, min(1.0, (px * dx + py * dy) / length))
                ex, ey = px - t * dx, py - t * dy
                distance = ex * ex + ey * ey
            if distance > worst:
                worst, worst_index = distance, i
        if worst_index >= 0 and worst > limit:
            keep[worst_index] = True
            stack.append((first, worst_index))
            stack.append((worst_index, last))
    return [point for point, kept in zip(points, keep) if kept]


def _bbox_ring(ring: list) -> list:
    lons, lats = [p[0] for p in ring], [p[1] for p in ring]
    west, south, east, north = min(lons), min(lats), max(lons), max(lats)
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]
