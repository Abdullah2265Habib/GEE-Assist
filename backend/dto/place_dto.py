"""A place found by name (city, region, country) that can be used as the Area of Interest."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlaceDTO:
    name: str           # short name, e.g. "Lahore"
    display_name: str   # full name with its parents, e.g. "Lahore, Punjab, Pakistan"
    kind: str           # what it is, e.g. "city", "district", "country"
    aoi: str            # GeoJSON geometry of the place's boundary (Polygon / MultiPolygon)
