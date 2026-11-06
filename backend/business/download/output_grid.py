"""The pixel grid a download is written on.

The AOI's bounding box is reprojected into the output CRS and covered with square
pixels of the requested scale. Every chunk (and every GEE request inside a chunk)
is a window of this one grid, so the pieces line up exactly when they are merged.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from backend.business.request.geojson_utils import geometry_bbox
from backend.config import BYTES_PER_PIXEL, get_dataset
from backend.dto import FormDTO
from backend.exceptions import ValidationError

# GEE's conversion for geographic CRSs: one degree is 111 319.49 m at the equator.
METRES_PER_DEGREE = 111_319.49


@dataclass(frozen=True)
class OutputGrid:
    crs: str
    west: float          # left edge, in CRS units
    north: float         # top edge, in CRS units
    pixel_size: float    # CRS units per pixel (degrees or metres)
    width: int           # pixels
    height: int          # pixels
    bands: tuple[str, ...]

    @property
    def row_bytes(self) -> int:
        """Bytes of one full-width row with every band (float32)."""
        return self.width * len(self.bands) * BYTES_PER_PIXEL

    @property
    def total_bytes(self) -> int:
        return self.row_bytes * self.height

    def row_top(self, row: int) -> float:
        """y coordinate of the top edge of ``row``."""
        return self.north - row * self.pixel_size

    @property
    def east(self) -> float:
        return self.west + self.width * self.pixel_size


def output_grid(form: FormDTO) -> OutputGrid:
    """Grid for a validated request (AOI, scale, bands and an EPSG ``crs``)."""
    if not form.aoi:
        raise ValidationError("The request has no area of interest.")
    geometry = json.loads(form.aoi)
    info = get_dataset(form.dataset)
    bands = tuple(form.bands) or (info.default_bands if info else ())
    if not bands:
        raise ValidationError("Select at least one band to download.")
    scale = form.scale or (info.default_scale if info else None)
    if not scale or scale <= 0:
        raise ValidationError("The request has no valid scale (metres per pixel).")

    west, south, east, north = _bounds_in_crs(geometry_bbox(geometry), form.crs)
    pixel_size = scale / METRES_PER_DEGREE if _is_geographic(form.crs) else float(scale)
    width = max(1, math.ceil((east - west) / pixel_size))
    height = max(1, math.ceil((north - south) / pixel_size))
    return OutputGrid(form.crs, west, north, pixel_size, width, height, bands)


def _is_geographic(crs: str) -> bool:
    from rasterio.crs import CRS

    return CRS.from_string(crs).is_geographic


def _bounds_in_crs(bbox: list[float], crs: str) -> tuple[float, float, float, float]:
    """(west, south, east, north) of a lon/lat bounding box in ``crs``."""
    if crs.upper() == "EPSG:4326":
        return tuple(bbox)  # type: ignore[return-value]
    from rasterio.warp import transform_bounds

    # densify the edges so curved edges in the target CRS are fully covered
    return transform_bounds("EPSG:4326", crs, *bbox, densify_pts=21)
