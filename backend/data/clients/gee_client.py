"""Class diagram: GEEClient. Fetches dataset chunks from Google Earth Engine.

A chunk is fetched as a grid of ``computePixels`` requests (each under GEE's 48 MB
limit, see ``gee_tiles``) on the chunk's own pixel grid, and the tiles are written
into one GeoTIFF. Finished tiles are listed in ``<chunk>.tiles.json`` next to the
file, so a paused or interrupted chunk continues with the next tile.

If Earth Engine runs out of memory or time on a tile, the tile is fetched as four
quarters instead (and those split again if needed, down to ``MIN_SPLIT_PIXELS``)
and stitched back together. Later tiles of the same request start at that smaller
size, so they do not fail first.

Responses are read as they stream in, so progress and speed are reported while a
tile arrives, not only once it is complete (see ``_ChunkReporter``).

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
from backend.data.clients.gee_tiles import Tile, plan_tiles
from backend.data.clients.i_gee_client import IGEEClient, ProgressCallback, StopCheck
from backend.dto import ChunkDTO, FormDTO
from backend.exceptions import GEEError, GEERequestTooHeavyError, GEESetupError, ValidationError

logger = logging.getLogger(__name__)

PARALLEL_REQUESTS = 8      # tiles requested from GEE at the same time
# Bytes per request as GEE counts them, well under its 48 MB cap: GEE computes a small
# request much sooner, so data starts arriving earlier and keeps arriving steadily.
REQUEST_BYTES = 4_000_000
MIN_SPLIT_PIXELS = 256 * 256  # a too-heavy tile is not split below this
STREAM_BLOCK = 64 * 1024      # bytes read at a time from a GEE response
READ_TIMEOUT = 600            # seconds GEE may take before sending a response


class _Stopped(Exception):
    """The download was paused or cancelled while a response was streaming in."""
NODATA = -9999.0           # value of pixels outside the AOI or without imagery


class GEEClient(IGEEClient):
    def __init__(
        self,
        project: str = "",
        parallel_requests: int = PARALLEL_REQUESTS,
        max_request_bytes: int = REQUEST_BYTES,
    ):
        self._project = project
        self._parallel = max(1, parallel_requests)
        self._max_request_bytes = max_request_bytes
        self._initialized = False
        self._lock = threading.Lock()
        self._splits: dict[str, int] = {}  # request -> times its tiles had to be split
        self._sessions = threading.local()  # one HTTP session per download thread

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
        reporter = _ChunkReporter(on_progress)
        with _ChunkFile(target, dst) as chunk_file:
            pool = ThreadPoolExecutor(max_workers=self._parallel, thread_name_prefix="gee-tile")
            try:
                queue = iter(pending)
                running: dict[Future, Tile] = {}

                key = _request_key(chunk)

                def submit_next() -> None:
                    tile = next(queue, None)
                    if tile is not None:
                        with self._lock:
                            splits = self._splits.get(key, 0)
                        size = tile.width * tile.height * len(chunk.bands) * BYTES_PER_PIXEL
                        on_bytes = reporter.receiver(tile.index, size)
                        running[pool.submit(self._fetch_pixels, image, chunk, tile, splits, on_bytes, stop)] = tile

                for _ in range(self._parallel):
                    submit_next()
                while running:
                    finished, _ = wait(running, return_when=FIRST_COMPLETED)
                    for future in finished:
                        tile = running.pop(future)
                        try:
                            pixels, splits = future.result()  # GEEError propagates to the caller
                        except _Stopped:
                            return False
                        with self._lock:
                            self._splits[key] = max(self._splits.get(key, 0), splits)
                        chunk_file.write(pixels, tile)
                        progress.add(tile.index)
                        reporter.written(tile.index, tile.width * tile.height * len(chunk.bands) * BYTES_PER_PIXEL)
                        if stop():
                            return False  # requests still in flight are abandoned
                        submit_next()
            finally:
                reporter.close()  # takes back the progress of tiles that were not written
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

    def _fetch_pixels(
        self, image: Any, chunk: ChunkDTO, tile: Tile, splits: int,
        on_bytes: "_BytesCallback", stop: StopCheck,
    ) -> tuple[Any, int]:
        """Pixels of ``tile`` (bands x height x width) and how many times the tile had to be split.
        ``splits`` > 0 starts with that many splits already."""
        if splits == 0 or not _can_split(tile):
            try:
                data = self._fetch_tile(image, chunk, tile, on_bytes, stop)
            except GEERequestTooHeavyError:
                if not _can_split(tile):
                    raise
                logger.info("Tile %s of chunk %s is too heavy for Earth Engine; fetching it in quarters",
                            tile.index, chunk.id)
                splits = 1
            else:
                return _decode_tile(data, tile, chunk), 0

        import numpy as np

        pixels = np.empty((len(chunk.bands), tile.height, tile.width), dtype="float32")
        start = splits - 1
        for part in _quarters(tile):
            part_pixels, part_splits = self._fetch_pixels(image, chunk, part, start, on_bytes, stop)
            pixels[:, part.row - tile.row:part.row - tile.row + part.height,
                   part.col - tile.col:part.col - tile.col + part.width] = part_pixels
            start = max(start, part_splits)  # the next quarters start as small as this one had to be
        return pixels, start + 1

    def _fetch_tile(
        self, image: Any, chunk: ChunkDTO, tile: Tile, on_bytes: "_BytesCallback", stop: StopCheck,
    ) -> bytes:
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
            return self._compute_pixels(request, on_bytes, stop)
        except _Stopped:
            raise
        except Exception as exc:
            raise _error(exc, self._project) from exc

    def _compute_pixels(self, request: dict, on_bytes: "_BytesCallback", stop: StopCheck) -> bytes:
        """``ee.data.computePixels``, but reading the response as it streams in.

        The Earth Engine library only returns a response once all of it has arrived,
        so the request it builds is sent here instead. If the library internals are
        not as expected, the library is called directly (no live progress).
        """
        ee = self._ee()
        try:
            from ee import serializer

            body = dict(request, expression=serializer.encode(request["expression"]))
            call = ee.data._get_cloud_projects_raw().image().computePixels(
                project=ee.data._get_projects_path(), body=body,
            )
            session = self._session(ee.data._get_state().credentials)
        except Exception:
            logger.debug("Streaming is not available; using ee.data.computePixels", exc_info=True)
            data = ee.data.computePixels(request)
            on_bytes(len(data), len(data))
            return data

        with session.request(call.method, call.uri, data=call.body, headers=call.headers,
                             stream=True, timeout=(30, READ_TIMEOUT)) as response:
            if response.status_code != 200:
                raise ee.EEException(_error_message(response))
            parts, wire = [], 0
            for block in response.iter_content(STREAM_BLOCK):
                if stop():
                    raise _Stopped()
                parts.append(block)
                now = response.raw.tell()  # bytes off the network (before any decompression)
                on_bytes(now - wire, len(block))
                wire = now
            return b"".join(parts)

    def _session(self, credentials: Any) -> Any:
        from google.auth.transport.requests import AuthorizedSession

        session = getattr(self._sessions, "session", None)
        if session is None or session.credentials is not credentials:
            session = AuthorizedSession(credentials)
            self._sessions.session = session
        return session


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
        SPARSE_OK="TRUE",  # blocks not downloaded yet take no disk space (even after a pause)
    )
    for index, band in enumerate(chunk.bands, start=1):
        dst.set_band_description(index, band)
    return dst


_BytesCallback = Any  # (bytes off the network, bytes of the response) -> None


class _ChunkReporter:
    """Reports a chunk's progress to the download service while its tiles stream in.

    While a tile arrives, the response bytes count as provisional progress (at most the
    tile's raster size); once the tile is written, its progress becomes exactly its
    raster size. When the chunk stops (paused, failed), the provisional progress of
    tiles that were not written is taken back, so the progress bar never runs ahead
    of the data on disk. Bytes from requests abandoned after that are ignored.
    """

    def __init__(self, on_progress: Optional[ProgressCallback]):
        self._on_progress = on_progress or (lambda raster, received: None)
        self._lock = threading.Lock()
        self._shown: dict[int, int] = {}     # tile index -> provisional progress reported
        self._streamed: dict[int, int] = {}  # tile index -> response bytes received so far
        self._closed = False

    def receiver(self, index: int, size: int) -> _BytesCallback:
        def on_bytes(network: int, payload: int) -> None:
            with self._lock:
                if self._closed:
                    return
                self._streamed[index] = self._streamed.get(index, 0) + payload
                shown = min(self._streamed[index], size)
                delta = shown - self._shown.get(index, 0)
                self._shown[index] = shown
                self._on_progress(delta, network)
        return on_bytes

    def written(self, index: int, size: int) -> None:
        with self._lock:
            delta = size - self._shown.pop(index, 0)
            self._streamed.pop(index, None)
            if delta:
                self._on_progress(delta, 0)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            unwritten = sum(self._shown.values())
            self._shown.clear()
            if unwritten:
                self._on_progress(-unwritten, 0)


def _error_message(response: Any) -> str:
    """The message of an Earth Engine error response."""
    try:
        return response.json()["error"]["message"]
    except Exception:
        return f"HTTP {response.status_code}: {response.text[:300]}"


def _decode_tile(data: bytes, tile: Tile, chunk: ChunkDTO) -> Any:
    """The pixels of a GeoTIFF returned by GEE, checked against the tile's shape."""
    from rasterio.io import MemoryFile

    with MemoryFile(data) as memory, memory.open() as src:
        pixels = src.read(out_dtype="float32")
    expected = (len(chunk.bands), tile.height, tile.width)
    if pixels.shape != expected:
        raise GEEError(f"GEE returned a tile of shape {pixels.shape}, expected {expected}.")
    return pixels


class _ChunkFile:
    """The chunk GeoTIFF being written. A tile is on disk once ``write`` returns."""

    def __init__(self, path: Path, dst: Any):
        self._path, self._dst = path, dst

    def write(self, pixels: Any, tile: Tile) -> None:
        import rasterio
        from rasterio.windows import Window

        self._dst.write(pixels, window=Window(tile.col, tile.row, tile.width, tile.height))
        # GDAL keeps written blocks in memory until the file is closed: close it so the tile
        # is on disk (disk usage shows it, a crash keeps it), then reopen for the next tile.
        self._dst.close()
        self._dst = rasterio.open(self._path, "r+")

    def __enter__(self) -> "_ChunkFile":
        return self

    def __exit__(self, *exc: Any) -> None:
        self._dst.close()


def _can_split(tile: Tile) -> bool:
    return tile.width * tile.height > MIN_SPLIT_PIXELS


def _quarters(tile: Tile) -> list[Tile]:
    """``tile`` cut in half each way (only one way if it is a single row or column)."""
    half_width, half_height = (tile.width + 1) // 2, (tile.height + 1) // 2
    parts = []
    for row in range(tile.row, tile.row + tile.height, half_height):
        for col in range(tile.col, tile.col + tile.width, half_width):
            parts.append(Tile(
                index=tile.index, col=col, row=row,
                width=min(half_width, tile.col + tile.width - col),
                height=min(half_height, tile.row + tile.height - row),
            ))
    return parts


def _request_key(chunk: ChunkDTO) -> str:
    """Identifies the request a chunk belongs to (chunks of one download share it)."""
    return json.dumps(chunk.request.to_dict() if chunk.request else {}, sort_keys=True, default=str)


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
    """GEESetupError for problems only the user can fix, GEERequestTooHeavyError when the request
    needs too much memory or time, GEEError (retried) for the rest."""
    message = _explain(exc, project)
    if _is_setup_problem(str(exc)):
        return GEESetupError(message)
    if _is_too_heavy(str(exc)):
        return GEERequestTooHeavyError(message)
    return GEEError(message)


def _is_too_heavy(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in (
        "memory limit exceeded", "out of memory", "computation timed out", "capacity exceeded",
    ))


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
    if _is_too_heavy(text):
        return (
            "Earth Engine ran out of memory computing this request. Shorten the date range or use "
            f"the mosaic composite, then press Retry. ({text})"
        )
    if "too many" in lowered or "quota" in lowered or "rate limit" in lowered:
        return "Earth Engine is busy or the quota is used up. The download will retry; try again later if it keeps failing."
    return f"Earth Engine refused the request: {text}"
