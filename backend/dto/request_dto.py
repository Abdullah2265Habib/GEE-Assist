from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Optional


@dataclass
class FormDTO:
    """Structured parameters GEE needs to fetch data (domain model: DataRequest).

    Filled either by the parameter form (UC-03 / UC-04) or, for natural-language
    input (UC-02), starts with only ``query_text`` and is completed later by the
    LLM (Interpret Query).
    """

    # --- what to fetch ---
    dataset: str = ""                                   # key in backend.config.datasets.DATASETS
    bands: list[str] = field(default_factory=list)
    scale: Optional[int] = None                         # metres / pixel
    max_cloud_cover: Optional[int] = None               # percent, optical datasets only
    composite: str = "median"                           # how the image collection is reduced

    # --- where ---
    aoi: str = ""                                       # GeoJSON geometry as a JSON string
    aoi_name: str = ""                                  # file name or place name

    # --- when ---
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    # --- what for ---
    analysis_type: str = ""                             # Water | Vegetation | LST | LULC
    processes: list[str] = field(default_factory=list)  # e.g. NDVI, EVI

    # --- origin ---
    source: str = "form"                                # "form" | "nl"
    query_text: str = ""                                # original natural-language request

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("start_date", "end_date"):
            if data[key] is not None:
                data[key] = data[key].isoformat()
        return data
