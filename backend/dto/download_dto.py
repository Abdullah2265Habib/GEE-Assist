"""DTOs for downloading datasets from Google Earth Engine (UC-05 Fetch Data).

Names follow the SRS class diagram and domain model (Chunk, DownloadJob, Dataset).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from backend.dto.request_dto import FormDTO

# ----------------------------------------------------------------------------- chunk status
CHUNK_PENDING = "pending"          # not fetched yet
CHUNK_DOWNLOADING = "downloading"  # being fetched from GEE
CHUNK_DOWNLOADED = "downloaded"    # its GeoTIFF is complete on disk
CHUNK_MERGED = "merged"            # folded into the job's merged GeoTIFF
CHUNK_FAILED = "failed"            # gave up after the retry limit


@dataclass
class ChunkDTO:
    """Domain model: Chunk. One horizontal strip of the requested raster.

    The chunker cuts the full output grid into strips no larger than the configured
    chunk size (500 MB by default). ``transform`` places the strip's top-left pixel
    in ``crs`` (affine terms a, b, c, d, e, f in rasterio order: x = a*col + b*row + c,
    y = d*col + e*row + f), so strips line up exactly when they are merged.
    """

    id: int                                     # 1-based, top strip first
    bounds: tuple[float, float, float, float]   # west, south, east, north in ``crs``
    crs: str
    transform: tuple[float, float, float, float, float, float]
    width: int                                  # pixels
    height: int                                 # pixels (rows of the strip)
    row_offset: int                             # first row of the strip in the full raster
    bands: list[str] = field(default_factory=list)
    size_bytes: int = 0                         # expected size (width * height * bands * 4)
    status: str = CHUNK_PENDING
    retries: int = 0
    file_path: str = ""
    downloaded_bytes: int = 0
    # What to fetch (dataset, dates, AOI ...). Shared by all chunks of a job, so it is
    # not written with each chunk; the job stores it once.
    request: Optional[FormDTO] = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("request")
        data["bounds"] = list(self.bounds)
        data["transform"] = list(self.transform)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any], request: Optional[FormDTO] = None) -> "ChunkDTO":
        values = {k: v for k, v in data.items() if k in cls.__dataclass_fields__ and k != "request"}
        values["bounds"] = tuple(values["bounds"])
        values["transform"] = tuple(values["transform"])
        return cls(**values, request=request)


@dataclass
class DatasetDTO:
    """Domain model: Dataset. A downloaded raster ready for analysis (UC-06)."""

    id: str
    source: str                   # GEE collection id, e.g. COPERNICUS/S2_SR_HARMONIZED
    path: str                     # the GeoTIFF on disk
    data_type: str = "GeoTIFF"
    bands: list[str] = field(default_factory=list)
    time_periods: int = 1         # composites over the date range count as one period
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetDTO":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
