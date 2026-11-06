from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Optional


@dataclass(frozen=True)
class EntityDTO:
    """A named entity recognised in a natural-language query."""

    label: str        # PLACE | DATE | DATASET | PROCESS | ANALYSIS | BAND | CLOUD_COVER | RESOLUTION | COMPOSITE
    text: str         # the words as the user wrote them
    value: str = ""   # normalised value: dataset key, process name, "20", "2024-06-01/2024-08-31", ...
    start: int = 0    # character offsets in the query
    end: int = 0


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

    # --- how to save it (download) ---
    crs: str = "EPSG:4326"                              # output projection; "AUTO_UTM" is resolved on validation
    output_dir: str = ""                                # folder the GeoTIFF(s) are written to

    # --- what for (optional: empty = download only) ---
    analysis_type: str = ""                             # "" | Water | Vegetation | LST | LULC
    processes: list[str] = field(default_factory=list)  # e.g. NDVI, EVI

    # --- origin ---
    source: str = "form"                                # "form" | "nl"
    query_text: str = ""                                # original natural-language request
    clarification: str = ""                             # LLM's question when the query is ambiguous (UC-02 7a)
    notes: list[str] = field(default_factory=list)      # what could not be taken from the query, and why
    entities: list[EntityDTO] = field(default_factory=list)  # named entities found in the query

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("start_date", "end_date"):
            if data[key] is not None:
                data[key] = data[key].isoformat()
        return data
