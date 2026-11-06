"""Class diagram: DownloadService (UC-05 Fetch Data, activity diagram 4.4.4 Start Download).

One background worker runs downloads one at a time; later ones wait in a queue.
For each chunk of the active job it:

1. fetches the chunk from GEE (``IDataFacade.fetch_chunk``), retrying failures up to
   ``retry_limit`` times with a growing pause;
2. merges it into the job's merged GeoTIFF as soon as there are two pieces, so the
   file grows 500 MB -> 1 GB -> 1.5 GB ... and at most one chunk waits on disk;
3. saves the job (``download.json``), so it can resume after a pause or a restart.

When the last chunk is merged, the file becomes ``<folder>/<folder name>.tif``.
"""

from __future__ import annotations

import copy
import logging
import os
import shutil
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from backend.business.download.chunk_merger import ChunkMerger
from backend.business.download.i_chunk_merger import IChunkMerger
from backend.business.download.i_chunker import IChunker
from backend.business.download.i_download_service import IDownloadService
from backend.business.download.job_store import MANIFEST_NAME, DownloadJobStore
from backend.business.download.naming import dataset_folder_name, unique_folder
from backend.business.download.speed_meter import SpeedMeter
from backend.config import get_dataset
from backend.config.download_settings import DEFAULT_RETRY_LIMIT, DownloadSettingsStore
from backend.data.i_data_facade import IDataFacade
from backend.dto import ChunkDTO, DatasetDTO, DownloadJobDTO, FormDTO
from backend.dto.download_dto import (
    CHUNK_DOWNLOADED,
    CHUNK_DOWNLOADING,
    CHUNK_FAILED,
    CHUNK_MERGED,
    CHUNK_PENDING,
    JOB_CANCELLED,
    JOB_COMPLETED,
    JOB_FAILED,
    JOB_PAUSED,
    JOB_QUEUED,
    JOB_RUNNING,
)
from backend.exceptions import GeeAssistError, GEESetupError, ValidationError

logger = logging.getLogger(__name__)

CHUNKS_FOLDER = "chunks"
RETRY_DELAY_SECONDS = 2.0   # first retry waits 2 s, the second 4 s, ...
PROGRESS_WINDOW = 60.0      # seconds of progress the ETA is based on


class DownloadService(IDownloadService):
    def __init__(
        self,
        data_facade: IDataFacade,
        chunker: IChunker,
        chunk_merger: IChunkMerger,
        download_dir: str | Path,
        retry_limit: int = DEFAULT_RETRY_LIMIT,
        job_store: Optional[DownloadJobStore] = None,
        settings: Optional[DownloadSettingsStore] = None,
        retry_delay: float = RETRY_DELAY_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._data_facade = data_facade
        self._chunker = chunker
        self._chunk_merger = chunk_merger
        self._download_dir = Path(download_dir)
        self._retry_limit = retry_limit
        self._store = job_store or DownloadJobStore()
        self._settings = settings or DownloadSettingsStore()
        self._retry_delay = retry_delay
        self._clock = clock

        self._lock = threading.RLock()
        self._wakeup = threading.Condition(self._lock)
        self._jobs: dict[str, DownloadJobDTO] = {}
        self._queue: deque[str] = deque()
        self._active_id: Optional[str] = None
        self._stop = threading.Event()      # asks the active job to stop (pause, cancel, shutdown)
        self._network = SpeedMeter(clock=clock)                       # bytes received from GEE
        self._progress = SpeedMeter(window=PROGRESS_WINDOW, clock=clock)  # progress-bar bytes, for the ETA
        self._closed = False

        for job in self._store.load_all():
            if job.status in (JOB_RUNNING, JOB_QUEUED):
                job.status = JOB_PAUSED  # interrupted when the app closed: resumes on request
            job.speed_bps, job.average_speed_bps, job.eta_seconds = 0.0, 0.0, None
            self._jobs[job.id] = job

        self._worker = threading.Thread(target=self._run, name="download-worker", daemon=True)
        self._worker.start()

    # ------------------------------------------------------------- IDownloadService
    def start_download(self, form: FormDTO) -> DownloadJobDTO:
        if not form.aoi:
            raise ValidationError("Choose an area of interest before downloading.")
        if get_dataset(form.dataset) is None:
            raise ValidationError("Choose a dataset before downloading.")
        chunks = self._chunker.split(form)
        parent = Path(form.output_dir) if form.output_dir else self._download_dir
        with self._lock:
            folder = unique_folder(parent, dataset_folder_name(form))
            for chunk in chunks:
                chunk.file_path = str(folder / CHUNKS_FOLDER / f"chunk_{chunk.id:03d}.tif")
            job = DownloadJobDTO(
                id=uuid.uuid4().hex[:12],
                name=folder.name,
                folder=str(folder),
                total_chunks=len(chunks),
                chunks=chunks,
                request=form,
                total_bytes=sum(chunk.size_bytes for chunk in chunks),
                created_at=_now(),
            )
            self._jobs[job.id] = job
            self._enqueue(job)
            return self._snapshot(job)

    def get_progress(self, job: DownloadJobDTO) -> DownloadJobDTO:
        with self._lock:
            current = self._job(job)
            self._update_speed(current)
            snapshot = self._snapshot(current)
        return _with_disk_size(snapshot)

    def retry_failed_chunks(self, job: DownloadJobDTO) -> DownloadJobDTO:
        with self._lock:
            current = self._job(job)
            if current.status == JOB_FAILED:
                for chunk in current.chunks:
                    if chunk.status == CHUNK_FAILED:
                        chunk.status, chunk.retries = CHUNK_PENDING, 0
                self._enqueue(current)
            return self._snapshot(current)

    def pause(self, job: DownloadJobDTO) -> DownloadJobDTO:
        with self._lock:
            current = self._job(job)
            if current.status == JOB_QUEUED:
                self._remove_from_queue(current)
                current.status = JOB_PAUSED
                self._store.save(current)
            elif current.status == JOB_RUNNING:
                current.status = JOB_PAUSED
                self._stop.set()  # the worker saves the job once it has stopped
            return self._snapshot(current)

    def resume(self, job: DownloadJobDTO) -> DownloadJobDTO:
        with self._lock:
            current = self._job(job)
            if current.status == JOB_FAILED:
                return self.retry_failed_chunks(current)
            if current.status == JOB_PAUSED:
                self._enqueue(current)
            return self._snapshot(current)

    def cancel(self, job: DownloadJobDTO) -> DownloadJobDTO:
        with self._lock:
            current = self._job(job)
            if current.is_finished:
                return self._snapshot(current)
            current.status = JOB_CANCELLED
            current.finished_at = _now()
            current.speed_bps, current.average_speed_bps, current.eta_seconds = 0.0, 0.0, None
            self._remove_from_queue(current)
            if self._active_id == current.id:
                self._stop.set()  # the worker deletes the folder once it has stopped
            else:
                self._delete_files(current)
            return self._snapshot(current)

    def list_jobs(self) -> list[DownloadJobDTO]:
        with self._lock:
            for job in self._jobs.values():
                self._update_speed(job)
            snapshots = [self._snapshot(job) for job in self._jobs.values()]
        return [_with_disk_size(job) for job in snapshots]  # outside the lock: it reads the disk

    def chunk_size_mb(self) -> int:
        return self._settings.load().chunk_size_mb

    def set_chunk_size_mb(self, size_mb: int) -> int:
        return self._settings.set_chunk_size_mb(size_mb).chunk_size_mb

    def is_gee_available(self) -> bool:
        return self._data_facade.validate_access()

    def shutdown(self, timeout: float = 5.0) -> None:
        """Pause the active download (it resumes next time) and stop the worker."""
        with self._lock:
            self._closed = True
            active = self._jobs.get(self._active_id) if self._active_id else None
            if active is not None and active.status == JOB_RUNNING:
                active.status = JOB_PAUSED
            self._stop.set()
            self._wakeup.notify_all()
        self._worker.join(timeout)

    # ------------------------------------------------------------- worker
    def _run(self) -> None:
        while True:
            with self._wakeup:
                while not self._queue and not self._closed:
                    self._wakeup.wait()
                if self._closed:
                    return
                job = self._jobs.get(self._queue.popleft())
                if job is None or job.status != JOB_QUEUED:
                    continue
                job.status, job.error = JOB_RUNNING, ""
                self._active_id = job.id
                self._stop.clear()
                self._network.start()
                self._progress.start()
                self._store.save(job)
            try:
                self._download(job)
            except Exception as exc:  # merge failed, disk full, ...
                logger.exception("Download %s failed", job.name)
                with self._lock:
                    if job.status == JOB_RUNNING:
                        job.status = JOB_FAILED
                        job.error = str(exc) or exc.__class__.__name__
            finally:
                with self._lock:
                    self._active_id = None
                    job.speed_bps = job.average_speed_bps = 0.0
                    self._network.reset()
                    self._progress.reset()
                    if job.status != JOB_COMPLETED:
                        job.eta_seconds = None
                    if job.status == JOB_CANCELLED:
                        self._delete_files(job)
                    else:
                        self._store.save(job)

    def _download(self, job: DownloadJobDTO) -> None:
        for chunk in job.chunks:
            if chunk.status == CHUNK_MERGED:
                continue
            if self._stop.is_set():
                return
            if chunk.status != CHUNK_DOWNLOADED and not self._fetch_with_retries(job, chunk):
                return  # paused, cancelled or failed
            self._merge_in(job, chunk)
        self._finish(job)

    def _fetch_with_retries(self, job: DownloadJobDTO, chunk: ChunkDTO) -> bool:
        while True:
            if self._stop.is_set():
                return False
            with self._lock:
                chunk.status = CHUNK_DOWNLOADING
            try:
                complete = self._data_facade.fetch_chunk(
                    chunk, chunk.file_path,
                    on_progress=lambda count, received: self._on_bytes(job, chunk, count, received),
                    should_stop=self._stop.is_set,
                )
            except (GEESetupError, ValidationError) as exc:
                # Setup or request problem: retrying cannot help. Retry after fixing it.
                with self._lock:
                    chunk.status = CHUNK_FAILED
                    job.status = JOB_FAILED
                    job.error = str(exc)
                return False
            except Exception as exc:
                if not isinstance(exc, GeeAssistError):
                    logger.warning("Chunk %s of %s failed", chunk.id, job.name, exc_info=True)
                with self._lock:
                    chunk.retries += 1
                    if chunk.retries > self._retry_limit:
                        chunk.status = CHUNK_FAILED
                        job.status = JOB_FAILED
                        job.error = f"Chunk {chunk.id} failed after {chunk.retries} attempts: {exc}"
                        return False
                    chunk.status = CHUNK_PENDING
                    job.error = f"Retrying chunk {chunk.id} ({chunk.retries}/{self._retry_limit}): {exc}"
                    self._store.save(job)
                if self._stop.wait(self._retry_delay * chunk.retries):
                    return False
                continue

            with self._lock:
                if not complete:
                    chunk.status = CHUNK_PENDING
                    return False
                chunk.status = CHUNK_DOWNLOADED
                chunk.downloaded_bytes = chunk.size_bytes
                job.completed_chunks = sum(c.status in (CHUNK_DOWNLOADED, CHUNK_MERGED) for c in job.chunks)
                job.downloaded_bytes = sum(c.downloaded_bytes for c in job.chunks)
                job.error = ""
                self._store.save(job)
            return True

    def _on_bytes(self, job: DownloadJobDTO, chunk: ChunkDTO, count: int, received: int) -> None:
        """``count`` raster bytes were written (progress bar); ``received`` bytes came over the network."""
        with self._lock:
            before = chunk.downloaded_bytes
            chunk.downloaded_bytes = min(chunk.size_bytes, before + count)
            job.downloaded_bytes = sum(c.downloaded_bytes for c in job.chunks)
            job.received_bytes += received
            self._network.add(received)
            self._progress.add(chunk.downloaded_bytes - before)
            self._update_speed(job)

    def _update_speed(self, job: DownloadJobDTO) -> None:
        """Speed and ETA of the running job, as of now (they drop while no data arrives)."""
        if job.id != self._active_id or job.status != JOB_RUNNING:
            return
        job.speed_bps = self._network.rate()
        job.average_speed_bps = self._network.average()
        progress_rate = self._progress.rate()
        remaining = max(0, job.total_bytes - job.downloaded_bytes)
        job.eta_seconds = remaining / progress_rate if progress_rate > 0 else None

    def _merge_in(self, job: DownloadJobDTO, chunk: ChunkDTO) -> None:
        """Fold a downloaded chunk into the job's merged file (the first chunk becomes it)."""
        with self._lock:
            merged = [c for c in job.chunks if c.status == CHUNK_MERGED]
            previous = job.merged_path
        if not merged:
            with self._lock:
                chunk.status = CHUNK_MERGED
                job.merged_path = chunk.file_path
                job.merged_bytes = Path(chunk.file_path).stat().st_size
                self._store.save(job)
            return

        prefix = ChunkMerger.combined_chunk(merged, DatasetDTO(id="", source="", path=previous))
        output = Path(job.folder) / CHUNKS_FOLDER / f"merged_{merged[0].id:03d}-{chunk.id:03d}.tif"
        started = self._clock()
        dataset = self._chunk_merger.merge([prefix, chunk], output_path=str(output))
        elapsed = max(self._clock() - started, 1e-3)
        with self._lock:
            chunk.status = CHUNK_MERGED
            job.merged_path = dataset.path
            job.merged_bytes = dataset.size_bytes
            job.merge_speed_bps = (prefix.size_bytes + chunk.size_bytes) / elapsed
            self._store.save(job)
        for old in {previous, chunk.file_path} - {dataset.path}:
            Path(old).unlink(missing_ok=True)

    def _finish(self, job: DownloadJobDTO) -> None:
        final = Path(job.folder) / f"{job.name}.tif"
        os.replace(job.merged_path, final)
        shutil.rmtree(Path(job.folder) / CHUNKS_FOLDER, ignore_errors=True)
        info = get_dataset(job.request.dataset) if job.request else None
        with self._lock:
            job.dataset = DatasetDTO(
                id=job.id,
                source=info.collection_id if info else "",
                path=str(final),
                bands=list(job.chunks[0].bands) if job.chunks else [],
                size_bytes=final.stat().st_size,
            )
            job.merged_path = str(final)
            job.merged_bytes = job.dataset.size_bytes
            job.downloaded_bytes = job.total_bytes
            job.status = JOB_COMPLETED
            job.eta_seconds = 0.0
            job.finished_at = _now()

    # ------------------------------------------------------------- helpers
    def _job(self, job: DownloadJobDTO) -> DownloadJobDTO:
        try:
            return self._jobs[job.id]
        except KeyError:
            raise ValidationError("That download no longer exists.") from None

    def _enqueue(self, job: DownloadJobDTO) -> None:
        job.status = JOB_QUEUED
        job.error = ""
        self._store.save(job)
        if job.id not in self._queue:
            self._queue.append(job.id)
        self._wakeup.notify_all()

    def _remove_from_queue(self, job: DownloadJobDTO) -> None:
        if job.id in self._queue:
            self._queue.remove(job.id)

    def _delete_files(self, job: DownloadJobDTO) -> None:
        """Delete a cancelled job's folder (only if it is the job's own folder)."""
        self._store.forget(job)
        folder = Path(job.folder)
        if folder.name == job.name and (folder / MANIFEST_NAME).exists():
            shutil.rmtree(folder, ignore_errors=True)

    @staticmethod
    def _snapshot(job: DownloadJobDTO) -> DownloadJobDTO:
        return copy.deepcopy(job)


def _with_disk_size(job: DownloadJobDTO) -> DownloadJobDTO:
    job.disk_bytes = 0 if job.status == JOB_CANCELLED else _folder_size(Path(job.folder))
    return job


def _folder_size(folder: Path) -> int:
    """Bytes of all files under ``folder`` (0 if it is gone)."""
    total = 0
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return 0
    for entry in entries:
        try:
            if entry.is_dir(follow_symlinks=False):
                total += _folder_size(Path(entry.path))
            elif entry.is_file(follow_symlinks=False):
                total += entry.stat(follow_symlinks=False).st_size
        except OSError:
            pass  # removed while we looked
    return total


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
