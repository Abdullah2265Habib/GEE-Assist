"""DTOs for looking at downloaded GeoTIFFs: what a file holds, how to show it, and the result."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class RasterInfoDTO:
    """What a GeoTIFF holds, read from the file (and its download name)."""

    path: str
    name: str                                   # file name without ".tif"
    width: int                                  # pixels
    height: int
    band_names: tuple[str, ...]                 # e.g. ("B2", "B3", "B4", "B8", "B11")
    crs: str                                    # e.g. "EPSG:4326"
    bounds: tuple[float, float, float, float]   # west, south, east, north in degrees (EPSG:4326)
    nodata: Optional[float]
    dtype: str
    size_bytes: int
    satellite: str = ""                         # from the download name, e.g. "Sentinel-2"
    start_date: str = ""                        # "YYYY-MM-DD", from the download name
    end_date: str = ""

    @property
    def band_count(self) -> int:
        return len(self.band_names)


@dataclass(frozen=True)
class ViewPresetDTO:
    """One way to show a GeoTIFF, e.g. true colour or NDVI."""

    key: str                                    # e.g. "true_colour", "ndvi", "band:B8"
    label: str                                  # shown to the user
    kind: str                                   # "rgb", "index", "classes" or "band"
    bands: tuple[str, ...]                      # the bands it uses (red, green, blue for "rgb")
    description: str = ""


@dataclass(frozen=True)
class LegendDTO:
    """How to read a rendered view: a colour scale or a list of classes."""

    kind: str                                   # "scale", "classes" or "rgb"
    title: str
    low: float = 0.0                            # "scale": the values at the two ends
    high: float = 0.0
    colours: tuple[str, ...] = ()               # "scale": colours from low to high; "classes": one per class
    labels: tuple[str, ...] = ()                # "classes": class names; "rgb": the red, green, blue bands


@dataclass
class RasterViewDTO:
    """A preview of a GeoTIFF drawn for one preset, ready to show."""

    preset: ViewPresetDTO
    rgba: object                                # numpy uint8 array (height, width, 4); no-data is transparent
    legend: LegendDTO
    width: int                                  # preview size in pixels
    height: int
    scale: float                                # GeoTIFF pixels per preview pixel (>= 1)
    notes: list[str] = field(default_factory=list)
