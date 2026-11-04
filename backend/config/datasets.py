"""Supported GEE datasets and the analyses each one supports.

Single source of truth for the parameter form drop-downs and for
RequestService.validate_form (UC-03 alternate flow 8c). Admin-managed
workflows (UC-11) will replace this later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class DatasetInfo:
    key: str
    name: str
    collection_id: str
    default_scale: int                       # metres / pixel
    bands: tuple[str, ...]
    default_bands: tuple[str, ...]
    supported_analyses: dict[str, tuple[str, ...]] = field(default_factory=dict)
    supports_cloud_filter: bool = False
    min_date: date = date(1984, 1, 1)


ANALYSIS_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Water": ("NDWI", "MNDWI", "WaterBodyDetection", "WaterAreaEstimation"),
    "Vegetation": ("NDVI", "EVI", "SAVI", "GNDVI"),
    "LST": ("LSTMapping", "LSTTemporalAnalysis"),
    "LULC": ("LULCChangeDetection", "LULCTransition"),
}

COMPOSITE_METHODS: tuple[str, ...] = ("median", "mean", "mosaic", "min", "max")


DATASETS: dict[str, DatasetInfo] = {
    "sentinel2_sr": DatasetInfo(
        key="sentinel2_sr",
        name="Sentinel-2 Surface Reflectance (Harmonized)",
        collection_id="COPERNICUS/S2_SR_HARMONIZED",
        default_scale=10,
        bands=("B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B9", "B11", "B12"),
        default_bands=("B2", "B3", "B4", "B8", "B11"),
        supported_analyses={
            "Water": ANALYSIS_CATEGORIES["Water"],
            "Vegetation": ANALYSIS_CATEGORIES["Vegetation"],
        },
        supports_cloud_filter=True,
        min_date=date(2017, 3, 28),
    ),
    "landsat8_l2": DatasetInfo(
        key="landsat8_l2",
        name="Landsat 8 Collection 2 Level-2",
        collection_id="LANDSAT/LC08/C02/T1_L2",
        default_scale=30,
        bands=("SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7", "ST_B10"),
        default_bands=("SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6"),
        supported_analyses={
            "Water": ANALYSIS_CATEGORIES["Water"],
            "Vegetation": ANALYSIS_CATEGORIES["Vegetation"],
            "LST": ANALYSIS_CATEGORIES["LST"],
        },
        supports_cloud_filter=True,
        min_date=date(2013, 4, 11),
    ),
    "modis_lst": DatasetInfo(
        key="modis_lst",
        name="MODIS Terra Land Surface Temperature 8-Day (MOD11A2)",
        collection_id="MODIS/061/MOD11A2",
        default_scale=1000,
        bands=("LST_Day_1km", "LST_Night_1km"),
        default_bands=("LST_Day_1km",),
        supported_analyses={"LST": ANALYSIS_CATEGORIES["LST"]},
        min_date=date(2000, 2, 18),
    ),
    "dynamic_world": DatasetInfo(
        key="dynamic_world",
        name="Dynamic World Land Use / Land Cover",
        collection_id="GOOGLE/DYNAMICWORLD/V1",
        default_scale=10,
        bands=("label", "water", "trees", "grass", "crops", "built", "bare"),
        default_bands=("label",),
        supported_analyses={"LULC": ANALYSIS_CATEGORIES["LULC"]},
        min_date=date(2015, 6, 27),
    ),
}


def get_dataset(key: str) -> DatasetInfo | None:
    return DATASETS.get(key)
