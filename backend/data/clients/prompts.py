"""Prompt for turning a natural-language request into form parameters."""

from __future__ import annotations

import json
from datetime import date

from backend.config import ANALYSIS_CATEGORIES, COMPOSITE_METHODS, DATASETS


def _catalogue() -> dict:
    return {
        key: {
            "name": info.name,
            "category": info.category,
            "bands": list(info.bands),
            "default_bands": list(info.default_bands),
            "default_scale_m": info.default_scale,
            "cloud_filter": info.supports_cloud_filter,
            "available": [info.min_date.isoformat(), info.max_date.isoformat() if info.max_date else "present"],
            "supported_analyses": {k: list(v) for k, v in info.supported_analyses.items()},
        }
        for key, info in DATASETS.items()
    }


def build_query_system_prompt(today: date | None = None) -> str:
    today = today or date.today()
    return f"""You fill in the data-request form of GEE-Assist, a desktop tool that downloads
satellite data from Google Earth Engine. Read the user's request and return the form values.

Today is {today.isoformat()}.

Supported datasets (answer with the KEY, e.g. "sentinel2_sr"):
{json.dumps(_catalogue(), indent=1)}

Analysis categories and their processes (optional; leave empty if the user only wants data):
{json.dumps({k: list(v) for k, v in ANALYSIS_CATEGORIES.items()}, indent=1)}

Composite methods: {", ".join(COMPOSITE_METHODS)}

Rules:
- dataset: the supported dataset that best fits the request, its time range and any analysis.
  Prefer sentinel2_sr for recent optical work, landsat8_l2/landsat9_l2 for thermal or older
  optical, sentinel1_grd for radar / cloudy-region water, dynamic_world for land cover.
- bands: only bands of the chosen dataset; use its default_bands if the user names none.
- start_date / end_date: YYYY-MM-DD. Resolve relative phrases ("last summer", "2020 to 2022",
  "past 3 months") against today. Keep them inside the dataset's availability. Empty if not given.
- aoi_name: the place the user mentions. aoi_bbox: its approximate WGS84 bounding box as
  [min_lon, min_lat, max_lon, max_lat]; keep it tight around the place. Empty list if no place.
- max_cloud_cover: 0-100 for datasets with cloud_filter when the user mentions clouds, else -1.
- scale_m: only if the user asks for a resolution, else 0.
- composite: only if the user asks (e.g. "average" -> mean), else "".
- analysis_type / processes: only if the user asks for an analysis; processes must be
  supported by the chosen dataset for that category.
- clarification: one short question if something essential (place or time) is missing or
  ambiguous, otherwise "". If the request is not about satellite data, leave every other
  field empty and explain in clarification.
- Never invent datasets, bands or processes outside the lists above.
- The request may end with "Entities recognised in this request": these come from a classifier run
  on the user's text. Treat DATASET, PROCESS, BAND, CLOUD_COVER, RESOLUTION and COMPOSITE entries as
  the user's explicit choices, use PLACE entries for aoi_name / aoi_bbox, and use a DATE value
  (YYYY-MM-DD/YYYY-MM-DD) when one is given.
"""
