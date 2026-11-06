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


# ----------------------------------------------------------------------------- job status
JOB_QUEUED = "queued"          # waiting for the job ahead of it to finish
JOB_RUNNING = "running"        # downloading or merging
JOB_PAUSED = "paused"          # stopped by the user; resumes where it left off
JOB_COMPLETED = "completed"
JOB_FAILED = "failed"          # a chunk failed after the retry limit; can be retried
JOB_CANCELLED = "cancelled"    # stopped by the user; its files are deleted

ACTIVE_JOB_STATES = (JOB_QUEUED, JOB_RUNNING, JOB_PAUSED, JOB_FAILED)
FINISHED_JOB_STATES = (JOB_COMPLETED, JOB_CANCELLED)


@dataclass
class DownloadJobDTO:
    """Domain model: DownloadJob. One dataset download, split into chunks.

    Downloaded chunks are merged as soon as there are two of them, so at any time
    the job folder holds one merged GeoTIFF plus at most the chunk being fetched.
    """

    id: str
    name: str                                   # dataset folder name, e.g. Sentinel-2_73.8231_33.2334
    folder: str                                 # absolute path of that folder
    status: str = JOB_QUEUED
    completed_chunks: int = 0
    total_chunks: int = 0
    chunks: list[ChunkDTO] = field(default_factory=list)
    request: Optional[FormDTO] = None
    total_bytes: int = 0                        # expected size of the whole dataset
    downloaded_bytes: int = 0
    merged_bytes: int = 0                       # size of the merged GeoTIFF so far
    received_bytes: int = 0                     # bytes actually received from GEE (all attempts)
    disk_bytes: int = 0                         # size of the job's files on disk right now
    merged_path: str = ""                       # the merged GeoTIFF so far (top chunks joined)
    speed_bps: float = 0.0                      # current download speed (last 2 s), bytes / second
    average_speed_bps: float = 0.0              # average speed since the download (re)started
    merge_speed_bps: float = 0.0                # speed of the running merge (0 when none), bytes / second
    eta_seconds: Optional[float] = None
    dataset: Optional[DatasetDTO] = None        # set once the job is completed
    error: str = ""
    created_at: str = ""                        # ISO timestamps
    finished_at: str = ""

    @property
    def progress(self) -> float:
        """Share of the expected bytes downloaded, 0.0 - 1.0."""
        if self.total_bytes <= 0:
            return 1.0 if self.status == JOB_COMPLETED else 0.0
        return min(1.0, self.downloaded_bytes / self.total_bytes)

    @property
    def is_finished(self) -> bool:
        return self.status in FINISHED_JOB_STATES

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["chunks"] = [chunk.to_dict() for chunk in self.chunks]
        data["request"] = self.request.to_dict() if self.request else None
        data["dataset"] = self.dataset.to_dict() if self.dataset else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DownloadJobDTO":
        values = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        request = FormDTO.from_dict(values["request"]) if values.get("request") else None
        values["request"] = request
        values["chunks"] = [ChunkDTO.from_dict(c, request) for c in values.get("chunks", [])]
        values["dataset"] = DatasetDTO.from_dict(values["dataset"]) if values.get("dataset") else None
        return cls(**values)
