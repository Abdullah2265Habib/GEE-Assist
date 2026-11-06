"""Class diagram: GEEClient. Fetches dataset chunks from Google Earth Engine.

A chunk is fetched as a grid of ``computePixels`` requests (each under GEE's 48 MB
limit, see ``gee_tiles``) on the chunk's own pixel grid, and the tiles are written
into one GeoTIFF. Finished tiles are listed in ``<chunk>.tiles.json`` next to the
file, so a paused or interrupted chunk continues with the next tile.

Earth Engine must be signed in once on the computer (``earthengine authenticate``)
and ``GEE_PROJECT`` in .env must name a Cloud project registered for Earth Engine.
"""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

from backend.config import BYTES_PER_PIXEL, get_dataset
from backend.data.clients.gee_tiles import TARGET_REQUEST_BYTES, Tile, plan_tiles
from backend.data.clients.i_gee_client import IGEEClient, ProgressCallback, StopCheck
from backend.dto import ChunkDTO, FormDTO
from backend.exceptions import GEEError, GEESetupError, ValidationError

logger = logging.getLogger(__name__)

PARALLEL_REQUESTS = 4      # tiles requested from GEE at the same time
NODATA = -9999.0           # value of pixels outside the AOI or without imagery


class GEEClient(IGEEClient):
    def __init__(
        self,
        project: str = "",
        parallel_requests: int = PARALLEL_REQUESTS,
        max_request_bytes: int = TARGET_REQUEST_BYTES,
    ):
        self._project = project
        self._parallel = max(1, parallel_requests)
        self._max_request_bytes = max_request_bytes
        self._initialized = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------- access
    def validate_access(self) -> bool:
        try:
            self._initialize()
            self._ee().Number(1).getInfo()
            return True
        except GEEError as exc:
            logger.info("Earth Engine is not available: %s", exc)
            return False
        except Exception:
            logger.warning("Earth Engine access check failed", exc_info=True)
            return False

    def _initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            if not self._project:
                raise GEESetupError(
                    "Earth Engine is not configured: set GEE_PROJECT in .env to a Google Cloud "
                    "project registered for Earth Engine."
                )
            try:
                self._ee().Initialize(project=self._project)
            except GEEError:
                raise
            except Exception as exc:
                raise _error(exc, self._project) from exc
            self._initialized = True

    @staticmethod
    def _ee() -> Any:
        try:
            import ee
        except ImportError as exc:
            raise GEESetupError("The Earth Engine library is missing: pip install earthengine-api") from exc
        return ee

    # ------------------------------------------------------------- chunks
    def fetch_chunk(
        self,
        chunk: ChunkDTO,
        path: str,
        on_progress: Optional[ProgressCallback] = None,
        should_stop: Optional[StopCheck] = None,
    ) -> bool:
        if chunk.request is None:
            raise GEEError("The chunk has no request to fetch.")
        stop = should_stop or (lambda: False)
        target = Path(path)
        progress = _TileProgress(target)
        tiles = plan_tiles(chunk.width, chunk.height, len(chunk.bands), max_bytes=self._max_request_bytes)
        pending = [tile for tile in tiles if tile.index not in progress.done]
        if not pending:
            progress.clear()
            return True

        self._initialize()
        image = self._build_image(chunk.request, chunk.bands)
        target.parent.mkdir(parents=True, exist_ok=True)
        dst = _open_chunk_file(target, chunk, resume=bool(progress.done))
        if dst is None:  # the partly written file is damaged (e.g. the app was killed): start over
            logger.warning("Chunk file %s cannot be reopened; downloading the chunk again", target)
            progress.clear()
            pending = tiles
            dst = _open_chunk_file(target, chunk, resume=False)
        with dst:
            pool = ThreadPoolExecutor(max_workers=self._parallel, thread_name_prefix="gee-tile")
            try:
                queue = iter(pending)
                running: dict[Future, Tile] = {}

                def submit_next() -> None:
                    tile = next(queue, None)
                    if tile is not None:
                        running[pool.submit(self._fetch_tile, image, chunk, tile)] = tile

                for _ in range(self._parallel):
                    submit_next()
                while running:
                    finished, _ = wait(running, return_when=FIRST_COMPLETED)
                    for future in finished:
                        tile = running.pop(future)
                        data = future.result()  # GEEError propagates to the caller
                        _write_tile(dst, data, tile, chunk)
                        progress.add(tile.index)
                        if on_progress:  # raster bytes added, matching the chunk's planned size
                            on_progress(tile.width * tile.height * len(chunk.bands) * BYTES_PER_PIXEL)
                        if stop():
                            return False  # requests still in flight are abandoned
                        submit_next()
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
        progress.clear()
        return True

    def _build_image(self, form: FormDTO, bands: list[str]) -> Any:
        """The composite image the request asks for, clipped to the AOI."""
        ee = self._ee()
        info = get_dataset(form.dataset)
        if info is None:
            raise ValidationError(f"Unknown dataset: {form.dataset!r}.")
        try:
            geometry = ee.Geometry(json.loads(form.aoi))
            collection = ee.ImageCollection(info.collection_id).filterBounds(geometry)
            if form.start_date and form.end_date:
                end = form.end_date + timedelta(days=1)  # GEE's end date is exclusive
                collection = collection.filterDate(form.start_date.isoformat(), end.isoformat())
            if form.max_cloud_cover is not None and info.cloud_property:
                collection = collection.filter(ee.Filter.lte(info.cloud_property, form.max_cloud_cover))
            if collection.size().getInfo() == 0:
                raise ValidationError(
                    f"No {info.name} images match this request. Try a longer date range, "
                    "a higher cloud limit or a different area."
                )
            composite = collection.mosaic() if form.composite == "mosaic" else getattr(collection, form.composite)()
            return composite.select(list(bands)).toFloat().clip(geometry).unmask(NODATA, False)
        except (GEEError, ValidationError):
            raise
        except Exception as exc:
            raise _error(exc, self._project) from exc

    def _fetch_tile(self, image: Any, chunk: ChunkDTO, tile: Tile) -> bytes:
        """GeoTIFF bytes of one tile, on the chunk's grid shifted to the tile's corner."""
        a, b, c, d, e, f = chunk.transform
        request = {
            "expression": image,
            "fileFormat": "GEO_TIFF",
            "grid": {
                "dimensions": {"width": tile.width, "height": tile.height},
                "affineTransform": {
                    "scaleX": a, "shearX": b, "translateX": c + a * tile.col + b * tile.row,
                    "shearY": d, "scaleY": e, "translateY": f + d * tile.col + e * tile.row,
                },
                "crsCode": chunk.crs,
            },
        }
        try:
            return self._ee().data.computePixels(request)
        except Exception as exc:
            raise _error(exc, self._project) from exc


# ----------------------------------------------------------------------------- GeoTIFF writing
def _open_chunk_file(path: Path, chunk: ChunkDTO, resume: bool):
    """Open the chunk GeoTIFF to continue writing it, or create it.

    Returns None if a partly written file cannot be reopened or does not match the chunk.
    """
    import rasterio
    from rasterio.transform import Affine

    if resume and path.exists():
        try:
            dst = rasterio.open(path, "r+")
        except Exception:
            return None
        if (dst.width, dst.height, dst.count) != (chunk.width, chunk.height, len(chunk.bands)):
            dst.close()
            return None
        return dst
    dst = rasterio.open(
        path, "w", driver="GTiff",
        width=chunk.width, height=chunk.height, count=len(chunk.bands), dtype="float32",
        crs=chunk.crs, transform=Affine(*chunk.transform), nodata=NODATA,
        tiled=True, blockxsize=256, blockysize=256, BIGTIFF="IF_SAFER",
    )
    for index, band in enumerate(chunk.bands, start=1):
        dst.set_band_description(index, band)
    return dst


def _write_tile(dst: Any, data: bytes, tile: Tile, chunk: ChunkDTO) -> None:
    from rasterio.io import MemoryFile
    from rasterio.windows import Window

    with MemoryFile(data) as memory, memory.open() as src:
        pixels = src.read(out_dtype="float32")
    expected = (len(chunk.bands), tile.height, tile.width)
    if pixels.shape != expected:
        raise GEEError(f"GEE returned a tile of shape {pixels.shape}, expected {expected}.")
    dst.write(pixels, window=Window(tile.col, tile.row, tile.width, tile.height))


class _TileProgress:
    """Indexes of the tiles already written to a chunk file, kept in ``<chunk>.tiles.json``."""

    def __init__(self, chunk_path: Path):
        self.path = chunk_path.with_name(chunk_path.name + ".tiles.json")
        self.done: set[int] = set()
        if self.path.exists() and chunk_path.exists():
            try:
                self.done = set(json.loads(self.path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError):
                self.done = set()

    def add(self, index: int) -> None:
        self.done.add(index)
        self.path.write_text(json.dumps(sorted(self.done)), encoding="utf-8")

    def clear(self) -> None:
        self.done.clear()
        self.path.unlink(missing_ok=True)


# ----------------------------------------------------------------------------- errors
def _error(exc: Exception, project: str) -> GEEError:
    """GEESetupError for problems only the user can fix, GEEError (retried) for the rest."""
    message = _explain(exc, project)
    return GEESetupError(message) if _is_setup_problem(str(exc)) else GEEError(message)


def _is_setup_problem(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in (
        "authenticate", "credentials", "authorize", "not registered", "permission",
        "has not been used in project", "is disabled",
    )) or ("not found" in lowered and "project" in lowered)


def _explain(exc: Exception, project: str) -> str:
    """A readable message for an Earth Engine error."""
    text = str(exc)
    lowered = text.lower()
    if "has not been used in project" in lowered or ("api" in lowered and "is disabled" in lowered):
        return (
            f"The Earth Engine API is not enabled for project '{project}'. Enable it at "
            f"https://console.developers.google.com/apis/api/earthengine.googleapis.com/overview?project={project} "
            "then wait a few minutes and press Retry."
        )
    if "authenticate" in lowered or "credentials" in lowered or "authorize" in lowered:
        return "Earth Engine is not signed in on this computer. Run `earthengine authenticate` once, then try again."
    if "not registered" in lowered or "permission" in lowered or ("not found" in lowered and "project" in lowered):
        return (
            f"The Cloud project '{project}' cannot use Earth Engine. Register it at "
            "https://code.earthengine.google.com/register or set GEE_PROJECT to another project."
        )
    if "too many" in lowered or "quota" in lowered or "rate limit" in lowered:
        return "Earth Engine is busy or the quota is used up. The download will retry; try again later if it keeps failing."
    return f"Earth Engine refused the request: {text}"
