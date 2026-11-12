"""Draws a GeoTIFF for a view preset: a preview image (RGBA) and its legend.

The file is read scaled down to at most ``max_size`` pixels on its longer side, so a
large download draws quickly. Colour composites and single bands are stretched
between their 2nd and 98th percentiles (a few very bright or dark pixels do not wash
out the picture). Indices use fixed ranges, so a colour means the same in every file
(e.g. NDWI above 0 is usually water); classes keep their fixed colours. No-data pixels
are transparent.
"""

from __future__ import annotations

import math

import numpy as np

from backend.business.map.colour_maps import DYNAMIC_WORLD_CLASSES, VEGETATION, VIRIDIS, WATER, ColourMap
from backend.dto.map_dto import LegendDTO, RasterInfoDTO, RasterViewDTO, ViewPresetDTO
from backend.exceptions import MapError

MAX_PREVIEW = 1600
STRETCH = (2.0, 98.0)  # percentiles shown as the darkest and brightest
INDEX_SCALES: dict[str, ColourMap] = {"ndvi": VEGETATION, "ndwi": WATER}
INDEX_RANGES: dict[str, tuple[float, float]] = {"ndvi": (-0.2, 0.8), "ndwi": (-0.5, 0.5)}


def render(info: RasterInfoDTO, preset: ViewPresetDTO, max_size: int = MAX_PREVIEW) -> RasterViewDTO:
    missing = [band for band in preset.bands if band not in info.band_names]
    if missing:
        raise MapError(f"{info.name} has no band {', '.join(missing)} for {preset.label}.")
    scale = max(1.0, max(info.width, info.height) / max_size)
    height, width = max(1, math.ceil(info.height / scale)), max(1, math.ceil(info.width / scale))
    bands, valid = _read(info, preset, width, height)

    if preset.kind == "rgb":
        rgb = np.stack([_stretch(band, valid)[0] for band in bands], axis=-1)
        rgb = (rgb * 255).round().astype(np.uint8)
        legend = LegendDTO("rgb", preset.label, labels=preset.bands)
    elif preset.kind == "classes":
        rgb, legend = _classes(bands[0], valid)
    else:
        values = _index(bands) if preset.kind == "index" else bands[0]
        if preset.kind == "index":
            valid = valid & np.isfinite(values)
        if preset.kind == "index":
            low, high = INDEX_RANGES.get(preset.key, (-1.0, 1.0))
            scaled = np.clip((values - low) / (high - low), 0.0, 1.0)
        else:
            scaled, low, high = _stretch(values, valid)
        colour_map = INDEX_SCALES.get(preset.key, VIRIDIS)
        rgb = colour_map.apply(scaled)
        legend = LegendDTO("scale", preset.label, low=low, high=high, colours=colour_map.colours())

    alpha = np.where(valid, 255, 0).astype(np.uint8)
    rgba = np.dstack([rgb, alpha])
    notes = [f"Shown at 1/{scale:.1f} of full resolution."] if scale > 1 else []
    if not valid.any():
        notes.append("Every pixel is no-data: nothing to show.")
    return RasterViewDTO(preset=preset, rgba=rgba, legend=legend, width=width, height=height, scale=scale,
                         notes=notes)


def _read(info: RasterInfoDTO, preset: ViewPresetDTO, width: int, height: int) -> tuple[list[np.ndarray], np.ndarray]:
    """The preset's bands at preview size, and where all of them have data."""
    import rasterio
    from rasterio.enums import Resampling

    resampling = Resampling.nearest if preset.kind == "classes" else Resampling.average
    indexes = [info.band_names.index(band) + 1 for band in preset.bands]
    try:
        with rasterio.open(info.path) as src:
            data = src.read(indexes, out_shape=(len(indexes), height, width), resampling=resampling,
                            out_dtype="float64")
    except rasterio.errors.RasterioIOError as exc:
        raise MapError(f"Cannot read {info.name}: {exc}") from exc
    valid = np.all(np.isfinite(data), axis=0)
    if info.nodata is not None:
        valid &= np.all(data != info.nodata, axis=0)
    return list(data), valid


def _stretch(values: np.ndarray, valid: np.ndarray):
    """``values`` scaled to 0-1 between their 2nd and 98th percentiles, and those two values."""
    if not valid.any():
        return np.zeros_like(values), 0.0, 0.0
    low, high = (float(v) for v in np.percentile(values[valid], STRETCH))
    if high <= low:
        high = low + 1e-9
    return np.clip((values - low) / (high - low), 0.0, 1.0), low, high


def _index(bands: list[np.ndarray]) -> np.ndarray:
    """(a - b) / (a + b), e.g. NDVI from NIR and red; not a number where a + b is 0."""
    a, b = bands
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(a + b != 0, (a - b) / (a + b), np.nan)


def _classes(values: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray, LegendDTO]:
    classes = np.where(valid, np.nan_to_num(values), -1).round().astype(np.int64)
    known = valid & (classes >= 0) & (classes < len(DYNAMIC_WORLD_CLASSES))
    palette = np.array([[int(colour[i:i + 2], 16) for i in (1, 3, 5)] for _, colour in DYNAMIC_WORLD_CLASSES],
                       dtype=np.uint8)
    rgb = np.zeros(values.shape + (3,), dtype=np.uint8)
    rgb[known] = palette[classes[known]]
    present = sorted(set(np.unique(classes[known]).tolist()))
    legend = LegendDTO("classes", "Land cover classes",
                       colours=tuple(DYNAMIC_WORLD_CLASSES[c][1] for c in present),
                       labels=tuple(DYNAMIC_WORLD_CLASSES[c][0] for c in present))
    return rgb, legend
