"""Supported GEE datasets and the analyses each one supports.

Single source of truth for the parameter form drop-downs and for
RequestService.validate_form (UC-03 alternate flow 8c). Admin-managed
workflows (UC-11) will replace this later.

``supported_analyses`` lists, per analysis category, only the processes the
dataset's bands can actually compute. Anything missing is shown greyed out
in the form.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class DatasetInfo:
    key: str
    name: str
    category: str                            # grouping in the dataset drop-down
    collection_id: str
    default_scale: int                       # metres / pixel
    bands: tuple[str, ...]
    default_bands: tuple[str, ...]
    supported_analyses: dict[str, tuple[str, ...]] = field(default_factory=dict)
    supports_cloud_filter: bool = False
    default_composite: str = "median"
    min_date: date = date(1984, 1, 1)
    max_date: Optional[date] = None          # None = still acquiring


ANALYSIS_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Water": ("NDWI", "MNDWI", "WaterBodyDetection", "WaterAreaEstimation"),
    "Vegetation": ("NDVI", "EVI", "SAVI", "GNDVI"),
    "LST": ("LSTMapping", "LSTTemporalAnalysis"),
    "LULC": ("LULCChangeDetection", "LULCTransition"),
}

COMPOSITE_METHODS: tuple[str, ...] = ("median", "mean", "mosaic", "min", "max", "mode")

# Order in which categories appear in the dataset drop-down.
DATASET_CATEGORIES: tuple[str, ...] = (
    "Optical (multispectral)",
    "Radar (SAR)",
    "Vegetation products",
    "Temperature",
    "Land cover",
    "Surface water",
)

_WATER = ANALYSIS_CATEGORIES["Water"]
_VEGETATION = ANALYSIS_CATEGORIES["Vegetation"]
_LST = ANALYSIS_CATEGORIES["LST"]
_LULC = ANALYSIS_CATEGORIES["LULC"]
_WATER_MASK_ONLY = ("WaterBodyDetection", "WaterAreaEstimation")

_S2_BANDS = ("B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B9", "B11", "B12")
_L89_BANDS = ("SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7", "ST_B10", "QA_PIXEL")
_L57_BANDS = ("SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7", "ST_B6", "QA_PIXEL")


_DATASET_LIST: tuple[DatasetInfo, ...] = (
    # ---------------------------------------------------------------- optical
    DatasetInfo(
        key="sentinel2_sr",
        name="Sentinel-2 Surface Reflectance (L2A)",
        category="Optical (multispectral)",
        collection_id="COPERNICUS/S2_SR_HARMONIZED",
        default_scale=10,
        bands=_S2_BANDS + ("SCL", "QA60"),
        default_bands=("B2", "B3", "B4", "B8", "B11"),
        supported_analyses={"Water": _WATER, "Vegetation": _VEGETATION},
        supports_cloud_filter=True,
        min_date=date(2017, 3, 28),
    ),
    DatasetInfo(
        key="sentinel2_toa",
        name="Sentinel-2 Top-of-Atmosphere (L1C)",
        category="Optical (multispectral)",
        collection_id="COPERNICUS/S2_HARMONIZED",
        default_scale=10,
        bands=_S2_BANDS[:10] + ("B10",) + _S2_BANDS[10:] + ("QA60",),
        default_bands=("B2", "B3", "B4", "B8", "B11"),
        supported_analyses={"Water": _WATER, "Vegetation": _VEGETATION},
        supports_cloud_filter=True,
        min_date=date(2015, 6, 27),
    ),
    DatasetInfo(
        key="landsat9_l2",
        name="Landsat 9 Collection 2 Level-2",
        category="Optical (multispectral)",
        collection_id="LANDSAT/LC09/C02/T1_L2",
        default_scale=30,
        bands=_L89_BANDS,
        default_bands=("SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6"),
        supported_analyses={"Water": _WATER, "Vegetation": _VEGETATION, "LST": _LST},
        supports_cloud_filter=True,
        min_date=date(2021, 10, 31),
    ),
    DatasetInfo(
        key="landsat8_l2",
        name="Landsat 8 Collection 2 Level-2",
        category="Optical (multispectral)",
        collection_id="LANDSAT/LC08/C02/T1_L2",
        default_scale=30,
        bands=_L89_BANDS,
        default_bands=("SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6"),
        supported_analyses={"Water": _WATER, "Vegetation": _VEGETATION, "LST": _LST},
        supports_cloud_filter=True,
        min_date=date(2013, 3, 18),
    ),
    DatasetInfo(
        key="landsat7_l2",
        name="Landsat 7 Collection 2 Level-2",
        category="Optical (multispectral)",
        collection_id="LANDSAT/LE07/C02/T1_L2",
        default_scale=30,
        bands=_L57_BANDS,
        default_bands=("SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5"),
        supported_analyses={"Water": _WATER, "Vegetation": _VEGETATION, "LST": _LST},
        supports_cloud_filter=True,
        min_date=date(1999, 5, 28),
    ),
    DatasetInfo(
        key="landsat5_l2",
        name="Landsat 5 Collection 2 Level-2",
        category="Optical (multispectral)",
        collection_id="LANDSAT/LT05/C02/T1_L2",
        default_scale=30,
        bands=_L57_BANDS,
        default_bands=("SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5"),
        supported_analyses={"Water": _WATER, "Vegetation": _VEGETATION, "LST": _LST},
        supports_cloud_filter=True,
        min_date=date(1984, 3, 16),
        max_date=date(2012, 5, 5),
    ),
    DatasetInfo(
        key="modis_sr_8day",
        name="MODIS Terra Surface Reflectance 8-Day (MOD09A1)",
        category="Optical (multispectral)",
        collection_id="MODIS/061/MOD09A1",
        default_scale=500,
        bands=tuple(f"sur_refl_b0{i}" for i in range(1, 8)),
        default_bands=("sur_refl_b01", "sur_refl_b02", "sur_refl_b03", "sur_refl_b04", "sur_refl_b06"),
        supported_analyses={"Water": _WATER, "Vegetation": _VEGETATION},
        min_date=date(2000, 2, 18),
    ),
    # ------------------------------------------------------------------- SAR
    DatasetInfo(
        key="sentinel1_grd",
        name="Sentinel-1 SAR GRD (C-band)",
        category="Radar (SAR)",
        collection_id="COPERNICUS/S1_GRD",
        default_scale=10,
        bands=("VV", "VH", "HH", "HV", "angle"),
        default_bands=("VV", "VH"),
        # Radar has no optical bands: only backscatter-based water masking.
        supported_analyses={"Water": _WATER_MASK_ONLY},
        min_date=date(2014, 10, 3),
    ),
    # ---------------------------------------------------- vegetation products
    DatasetInfo(
        key="modis_vi_16day",
        name="MODIS Terra Vegetation Indices 16-Day 250 m (MOD13Q1)",
        category="Vegetation products",
        collection_id="MODIS/061/MOD13Q1",
        default_scale=250,
        bands=("NDVI", "EVI", "SummaryQA"),
        default_bands=("NDVI", "EVI"),
        supported_analyses={"Vegetation": ("NDVI", "EVI")},
        min_date=date(2000, 2, 18),
    ),
    # ----------------------------------------------------------- temperature
    DatasetInfo(
        key="modis_lst",
        name="MODIS Terra Land Surface Temperature 8-Day (MOD11A2)",
        category="Temperature",
        collection_id="MODIS/061/MOD11A2",
        default_scale=1000,
        bands=("LST_Day_1km", "LST_Night_1km"),
        default_bands=("LST_Day_1km",),
        supported_analyses={"LST": _LST},
        min_date=date(2000, 2, 18),
    ),
    DatasetInfo(
        key="modis_lst_aqua",
        name="MODIS Aqua Land Surface Temperature 8-Day (MYD11A2)",
        category="Temperature",
        collection_id="MODIS/061/MYD11A2",
        default_scale=1000,
        bands=("LST_Day_1km", "LST_Night_1km"),
        default_bands=("LST_Day_1km",),
        supported_analyses={"LST": _LST},
        min_date=date(2002, 7, 4),
    ),
    DatasetInfo(
        key="era5_land_daily",
        name="ERA5-Land Daily Aggregated (climate reanalysis)",
        category="Temperature",
        collection_id="ECMWF/ERA5_LAND/DAILY_AGGR",
        default_scale=11132,
        bands=("skin_temperature", "temperature_2m", "dewpoint_temperature_2m", "total_precipitation_sum"),
        default_bands=("skin_temperature", "temperature_2m"),
        supported_analyses={"LST": _LST},
        default_composite="mean",
        min_date=date(1950, 1, 2),
    ),
    # ------------------------------------------------------------ land cover
    DatasetInfo(
        key="dynamic_world",
        name="Dynamic World Land Use / Land Cover (10 m)",
        category="Land cover",
        collection_id="GOOGLE/DYNAMICWORLD/V1",
        default_scale=10,
        bands=("label", "water", "trees", "grass", "flooded_vegetation", "crops",
               "shrub_and_scrub", "built", "bare", "snow_and_ice"),
        default_bands=("label",),
        supported_analyses={"LULC": _LULC},
        default_composite="mode",
        min_date=date(2015, 6, 27),
    ),
    DatasetInfo(
        key="modis_landcover",
        name="MODIS Land Cover Type Yearly 500 m (MCD12Q1)",
        category="Land cover",
        collection_id="MODIS/061/MCD12Q1",
        default_scale=500,
        bands=("LC_Type1", "LC_Type2", "LC_Type3", "LC_Type4", "LC_Type5"),
        default_bands=("LC_Type1",),
        supported_analyses={"LULC": _LULC},
        default_composite="mode",
        min_date=date(2001, 1, 1),
    ),
    # --------------------------------------------------------- surface water
    DatasetInfo(
        key="jrc_water_monthly",
        name="JRC Global Surface Water Monthly History",
        category="Surface water",
        collection_id="JRC/GSW1_4/MonthlyHistory",
        default_scale=30,
        bands=("water",),
        default_bands=("water",),
        supported_analyses={"Water": _WATER_MASK_ONLY},
        default_composite="mode",
        min_date=date(1984, 3, 16),
        max_date=date(2021, 12, 31),
    ),
)

DATASETS: dict[str, DatasetInfo] = {d.key: d for d in _DATASET_LIST}


def get_dataset(key: str) -> DatasetInfo | None:
    return DATASETS.get(key)


def datasets_by_category() -> dict[str, list[DatasetInfo]]:
    grouped: dict[str, list[DatasetInfo]] = {c: [] for c in DATASET_CATEGORIES}
    for info in _DATASET_LIST:
        grouped.setdefault(info.category, []).append(info)
    return {c: items for c, items in grouped.items() if items}


# ----------------------------------------------------------------------------- query vocabulary
# Phrases users write for each dataset / process. Used by the query entity
# classifier (backend/business/request/query_entities.py). Hyphens and spaces
# are interchangeable ("sentinel-2" also matches "sentinel 2" and "sentinel2").
DATASET_ALIASES: dict[str, tuple[str, ...]] = {
    "sentinel2_sr": ("sentinel-2", "sentinel-2 sr", "sentinel-2 l2a", "sentinel-2 surface reflectance", "s2"),
    "sentinel2_toa": ("sentinel-2 l1c", "sentinel-2 toa", "sentinel-2 top of atmosphere"),
    "landsat9_l2": ("landsat-9", "landsat 9 l2"),
    "landsat8_l2": ("landsat-8", "landsat 8 l2"),
    "landsat7_l2": ("landsat-7", "landsat 7 l2"),
    "landsat5_l2": ("landsat-5", "landsat 5 l2", "landsat 5 tm"),
    "modis_sr_8day": ("mod09a1", "modis surface reflectance", "modis reflectance"),
    "sentinel1_grd": ("sentinel-1", "s1", "sar", "radar", "sentinel-1 sar"),
    "modis_vi_16day": ("mod13q1", "modis ndvi", "modis evi", "modis vegetation"),
    "modis_lst": ("mod11a2", "modis lst", "modis terra lst", "modis land surface temperature"),
    "modis_lst_aqua": ("myd11a2", "modis aqua", "aqua lst", "modis aqua lst"),
    "era5_land_daily": ("era5", "era5-land", "era-5", "era5 land", "climate reanalysis"),
    "dynamic_world": ("dynamic world",),
    "modis_landcover": ("mcd12q1", "modis land cover", "modis landcover"),
    "jrc_water_monthly": ("jrc", "jrc water", "global surface water", "jrc global surface water"),
}

PROCESS_ALIASES: dict[str, tuple[str, ...]] = {
    "NDVI": ("ndvi", "normalized difference vegetation index", "normalised difference vegetation index"),
    "EVI": ("evi", "enhanced vegetation index"),
    "SAVI": ("savi", "soil adjusted vegetation index", "soil-adjusted vegetation index"),
    "GNDVI": ("gndvi", "green ndvi"),
    "NDWI": ("ndwi", "normalized difference water index", "normalised difference water index"),
    "MNDWI": ("mndwi", "modified ndwi", "modified normalized difference water index"),
    "WaterBodyDetection": ("water body", "water bodies", "waterbodies", "flood", "floods", "flooding",
                           "flood mapping", "inundation", "surface water extent"),
    "WaterAreaEstimation": ("water area", "area of water", "water surface area", "water extent"),
    "LSTMapping": ("land surface temperature", "lst", "surface temperature", "temperature map"),
    "LSTTemporalAnalysis": ("temperature trend", "temperature trends", "temperature change", "warming trend",
                            "heat trend"),
    "LULCChangeDetection": ("land cover change", "land use change", "lulc change", "lulc", "urban growth",
                            "urban expansion", "urbanisation", "urbanization", "deforestation"),
    "LULCTransition": ("land cover transition", "land use transition", "lulc transition"),
}

# Words that point to an analysis category without naming a process.
ANALYSIS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Vegetation": ("vegetation", "crop", "crops", "greenness", "forest", "plant health"),
    "Water": ("water", "lake", "lakes", "river", "rivers", "reservoir", "wetland", "wetlands"),
    "LST": ("temperature", "thermal", "heat", "heatwave", "urban heat"),
    "LULC": ("land cover", "land use", "landcover", "urban", "built-up", "built up"),
}
