"""DownloadService with a fake Earth Engine that writes real GeoTIFF chunks."""

import json
import threading
import time
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import Affine  # noqa: E402

from backend.business.download import Chunker, ChunkMerger, DownloadJobStore, DownloadService  # noqa: E402
from backend.business.download.naming import dataset_folder_name  # noqa: E402
from backend.config.download_settings import DownloadSettings, DownloadSettingsStore  # noqa: E402
from backend.dto import FormDTO  # noqa: E402
from backend.dto.download_dto import (  # noqa: E402
    CHUNK_FAILED,
    CHUNK_MERGED,
    JOB_CANCELLED,
    JOB_COMPLETED,
    JOB_FAILED,
    JOB_PAUSED,
    JOB_QUEUED,
    JOB_RUNNING,
)
from backend.exceptions import GEEError, GEERequestTooHeavyError, GEESetupError, ValidationError  # noqa: E402

# 0.05 degree square at 10 m: 557 x 557 px, 1 band -> ~1.24 MB; with 1 MB chunks -> 2 chunks.
AOI = {"type": "Polygon", "coordinates": [[[73.0, 31.0], [73.05, 31.0], [73.05, 31.05], [73.0, 31.05], [73.0, 31.0]]]}


class FakeData:
    """Writes each chunk filled with its id. Can fail, block or be stopped part-way."""

    def __init__(self):
        self.failures: dict[int, int] = {}   # chunk id -> failures left
        self.setup_error: Exception | None = None
        self.gate: threading.Event | None = None
        self.before_gate: tuple[int, int] | None = None  # (raster, received) bytes reported before waiting
        self.calls: list[int] = []
        self.gee_ok = True

    def fetch_chunk(self, chunk, path, on_progress=None, should_stop=None):
        self.calls.append(chunk.id)
        if self.setup_error:
            raise self.setup_error
        if self.failures.get(chunk.id, 0) > 0:
            self.failures[chunk.id] -= 1
            raise GEEError("Earth Engine is busy")
        if self.gate is not None:  # wait until the test opens the gate (or the job is stopped)
            if self.before_gate and on_progress:
                on_progress(*self.before_gate)
            while not self.gate.wait(0.01):
                if should_stop and should_stop():
                    return False
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(path, "w", driver="GTiff", width=chunk.width, height=chunk.height,
                           count=len(chunk.bands), dtype="float32", crs=chunk.crs,
                           transform=Affine(*chunk.transform)) as ds:
            ds.write(np.full((len(chunk.bands), chunk.height, chunk.width), chunk.id, "float32"))
        if on_progress:
            on_progress(chunk.size_bytes, chunk.size_bytes)
        return True

    def validate_access(self):
        return self.gee_ok


@pytest.fixture
def env(tmp_path):
    settings = DownloadSettingsStore(tmp_path / "download_settings.json")
    settings.save(DownloadSettings(chunk_size_mb=1, retry_limit=2))
    data = FakeData()
    services = []

    def make(**kwargs):
        service = DownloadService(
            data, Chunker(settings), ChunkMerger(), tmp_path / "default",
            retry_limit=kwargs.pop("retry_limit", 2),
            job_store=DownloadJobStore(tmp_path / "download_jobs.json"),
            settings=settings, retry_delay=0.01, **kwargs,
        )
        services.append(service)
        return service

    yield make, data, tmp_path
    for service in services:
        service.shutdown(timeout=2)


def _form(tmp_path, **overrides) -> FormDTO:
    values = dict(dataset="sentinel2_sr", bands=["B4"], scale=10, aoi=json.dumps(AOI),
                  crs="EPSG:4326", output_dir=str(tmp_path / "out"))
    values.update(overrides)
    return FormDTO(**values)


def _wait(service, job, *states, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = service.get_progress(job)
        if job.status in states:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job stayed {job.status}, expected {states}")


def _strip_values(job) -> list[int]:
    with rasterio.open(job.dataset.path) as src:
        band = src.read(1)
    starts = np.cumsum([0] + [c.height for c in job.chunks][:-1])
    return [int(band[row, 0]) for row in starts]


# ------------------------------------------------------------------ speed and ETA
def test_speed_is_measured_live_and_drops_while_nothing_arrives(env):
    make, data, tmp_path = env
    now = [1000.0]
    service = make(clock=lambda: now[0])
    data.gate, data.before_gate = threading.Event(), (300_000, 200_000)  # 300 kB of raster in 200 kB sent
    job = service.start_download(_form(tmp_path))
    deadline = time.monotonic() + 10
    while service.get_progress(job).downloaded_bytes == 0:
        assert time.monotonic() < deadline, "no progress reported"
        time.sleep(0.01)

    now[0] = 1002.0  # 2 s after the download started: the bytes are within the 2 s window
    job = service.get_progress(job)
    assert job.status == JOB_RUNNING
    assert job.speed_bps == pytest.approx(100_000)          # bytes received over the network / 2 s
    assert job.average_speed_bps == pytest.approx(100_000)

    now[0] = 1010.0  # nothing more for 10 s: like Task Manager, the current speed is 0
    job = service.get_progress(job)
    assert job.speed_bps == 0
    assert job.average_speed_bps == pytest.approx(20_000)
    assert job.eta_seconds == pytest.approx((job.total_bytes - 300_000) / 30_000)  # 20 s of progress: steadier

    now[0] = 1040.0  # nothing for 40 s: no ETA any more
    job = service.get_progress(job)
    assert job.speed_bps == 0 and job.eta_seconds is None
    assert job.average_speed_bps == pytest.approx(200_000 / 40)
    assert [j.speed_bps for j in service.list_jobs()] == [0]

    data.gate.set()
    job = _wait(service, job, JOB_COMPLETED)
    assert job.speed_bps == 0 and job.average_speed_bps == 0


def test_merging_speed_is_live_while_a_merge_runs(env, monkeypatch):
    make, data, tmp_path = env
    inside, release = threading.Event(), threading.Event()
    original = ChunkMerger.merge

    def slow_merge(self, chunks, output_path=None, on_progress=None):
        on_progress(5_000_000)
        inside.set()
        release.wait(5)
        return original(self, chunks, output_path)

    monkeypatch.setattr(ChunkMerger, "merge", slow_merge)
    service = make()
    job = service.start_download(_form(tmp_path))
    assert inside.wait(10), "the merge did not start"

    assert service.get_progress(job).merge_speed_bps > 0  # while merging
    release.set()
    job = _wait(service, job, JOB_COMPLETED)
    assert job.merge_speed_bps == 0                       # no merge running
    assert service.list_jobs()[0].disk_bytes == 0         # only the running download is measured on disk


# ------------------------------------------------------------------ the full download
def test_download_is_split_fetched_merged_and_named(env):
    make, data, tmp_path = env
    service = make()
    job = service.start_download(_form(tmp_path))

    assert job.total_chunks == 2
    assert job.name == "Sentinel-2_73.0250_31.0250"  # the request has no dates
    job = _wait(service, job, JOB_COMPLETED)

    final = Path(job.folder) / f"{job.name}.tif"
    assert job.dataset.path == str(final) and final.exists()
    assert Path(job.folder).parent == tmp_path / "out"
    assert sorted(p.name for p in Path(job.folder).iterdir()) == [f"{job.name}.tif", "download.json"]
    assert _strip_values(job) == [1, 2]
    assert job.progress == 1.0 and job.completed_chunks == 2
    assert all(c.status == CHUNK_MERGED for c in job.chunks)
    assert job.dataset.source == "COPERNICUS/S2_SR_HARMONIZED"
    assert job.received_bytes == job.total_bytes  # the fake sends exactly the planned bytes
    assert job.disk_bytes == sum(p.stat().st_size for p in Path(job.folder).iterdir())


def test_merged_file_grows_as_each_chunk_arrives(env, monkeypatch):
    """chunk 1 + chunk 2 -> one file, then + chunk 3, then + chunk 4."""
    make, data, tmp_path = env
    merges = []
    original = ChunkMerger.merge

    def recording_merge(self, chunks, output_path=None, on_progress=None):
        merges.append([(c.row_offset, c.height) for c in chunks])
        return original(self, chunks, output_path)

    monkeypatch.setattr(ChunkMerger, "merge", recording_merge)
    service = make()
    job = _wait(service, service.start_download(_form(tmp_path, bands=["B2", "B3", "B4"])), JOB_COMPLETED)

    heights = [c.height for c in job.chunks]
    assert len(heights) == 4
    assert merges == [
        [(0, heights[0]), (heights[0], heights[1])],
        [(0, sum(heights[:2])), (sum(heights[:2]), heights[2])],
        [(0, sum(heights[:3])), (sum(heights[:3]), heights[3])],
    ]
    assert _strip_values(job) == [1, 2, 3, 4]


def test_single_chunk_download(env):
    make, _, tmp_path = env
    service = make()
    job = _wait(service, service.start_download(_form(tmp_path, scale=30)), JOB_COMPLETED)
    assert job.total_chunks == 1 and Path(job.dataset.path).exists()


def test_same_request_twice_gets_a_second_folder(env):
    make, _, tmp_path = env
    service = make()
    first = _wait(service, service.start_download(_form(tmp_path)), JOB_COMPLETED)
    second = _wait(service, service.start_download(_form(tmp_path)), JOB_COMPLETED)
    assert Path(second.folder).name == f"{first.name}_2"


def test_downloads_run_one_at_a_time(env):
    make, data, tmp_path = env
    data.gate = threading.Event()
    service = make()
    first = service.start_download(_form(tmp_path))
    second = service.start_download(_form(tmp_path))

    _wait(service, first, JOB_RUNNING)
    assert service.get_progress(second).status == JOB_QUEUED
    data.gate.set()
    _wait(service, second, JOB_COMPLETED)


def test_request_without_an_area_is_refused(env):
    make, _, tmp_path = env
    with pytest.raises(ValidationError):
        make().start_download(_form(tmp_path, aoi=""))


# ------------------------------------------------------------------ retries
def test_failed_chunk_is_retried(env):
    make, data, tmp_path = env
    data.failures = {1: 2}  # fails twice, then works (retry limit 2)
    service = make()
    job = _wait(service, service.start_download(_form(tmp_path)), JOB_COMPLETED)
    assert data.calls.count(1) == 3 and job.chunks[0].retries == 2


def test_chunk_failing_past_the_retry_limit_fails_the_job(env):
    make, data, tmp_path = env
    data.failures = {2: 10}
    service = make()
    job = _wait(service, service.start_download(_form(tmp_path)), JOB_FAILED)

    assert job.chunks[1].status == CHUNK_FAILED
    assert "Chunk 2 failed after 3 attempts" in job.error
    assert job.chunks[0].status == CHUNK_MERGED  # finished work is kept


def test_setup_problem_fails_at_once_without_retries(env):
    make, data, tmp_path = env
    data.setup_error = GEESetupError("The Earth Engine API is not enabled for project 'p'.")
    service = make()
    job = _wait(service, service.start_download(_form(tmp_path)), JOB_FAILED)

    assert data.calls == [1]  # tried once, no retries
    assert job.error == "The Earth Engine API is not enabled for project 'p'."
    assert job.chunks[0].status == CHUNK_FAILED and job.chunks[0].retries == 0

    data.setup_error = None  # the user enabled the API
    assert _wait(service, service.retry_failed_chunks(job), JOB_COMPLETED).progress == 1.0


def test_too_heavy_request_fails_at_once_without_retries(env):
    make, data, tmp_path = env
    data.setup_error = GEERequestTooHeavyError("Earth Engine ran out of memory computing this request.")
    service = make()
    job = _wait(service, service.start_download(_form(tmp_path)), JOB_FAILED)

    assert data.calls == [1]  # the same request would fail again: no retries
    assert "ran out of memory" in job.error and job.chunks[0].retries == 0


def test_request_without_images_fails_at_once(env):
    make, data, tmp_path = env
    data.setup_error = ValidationError("No Sentinel-2 images match this request.")
    service = make()
    job = _wait(service, service.start_download(_form(tmp_path)), JOB_FAILED)
    assert data.calls == [1] and "No Sentinel-2 images" in job.error


def test_retry_failed_chunks_finishes_the_job(env):
    make, data, tmp_path = env
    data.failures = {2: 3}
    service = make()
    job = _wait(service, service.start_download(_form(tmp_path)), JOB_FAILED)

    data.failures = {}
    job = _wait(service, service.retry_failed_chunks(job), JOB_COMPLETED)
    assert data.calls.count(1) == 1  # chunk 1 was not downloaded again
    assert _strip_values(job) == [1, 2]


# ------------------------------------------------------------------ pause, resume, cancel
def test_pause_and_resume(env):
    make, data, tmp_path = env
    data.gate = threading.Event()
    service = make()
    job = service.start_download(_form(tmp_path))
    _wait(service, job, JOB_RUNNING)

    job = _wait(service, service.pause(job), JOB_PAUSED)
    time.sleep(0.05)
    assert service.get_progress(job).status == JOB_PAUSED  # stays paused

    data.gate.set()
    job = _wait(service, service.resume(job), JOB_COMPLETED)
    assert _strip_values(job) == [1, 2]


def test_pausing_a_queued_download_keeps_it_out_of_the_queue(env):
    make, data, tmp_path = env
    data.gate = threading.Event()
    service = make()
    first = service.start_download(_form(tmp_path))
    second = service.start_download(_form(tmp_path))
    service.pause(second)

    data.gate.set()
    _wait(service, first, JOB_COMPLETED)
    time.sleep(0.05)
    assert service.get_progress(second).status == JOB_PAUSED


def test_cancel_stops_the_download_and_deletes_its_folder(env):
    make, data, tmp_path = env
    data.gate = threading.Event()
    service = make()
    job = service.start_download(_form(tmp_path))
    _wait(service, job, JOB_RUNNING)

    job = service.cancel(job)
    assert job.status == JOB_CANCELLED
    deadline = time.monotonic() + 5
    while Path(job.folder).exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not Path(job.folder).exists()


def test_cancel_a_queued_download(env):
    make, data, tmp_path = env
    data.gate = threading.Event()
    service = make()
    service.start_download(_form(tmp_path))
    queued = service.start_download(_form(tmp_path))

    queued = service.cancel(queued)
    assert queued.status == JOB_CANCELLED and not Path(queued.folder).exists()
    data.gate.set()


def test_completed_download_cannot_be_cancelled(env):
    make, _, tmp_path = env
    service = make()
    job = _wait(service, service.start_download(_form(tmp_path)), JOB_COMPLETED)
    assert service.cancel(job).status == JOB_COMPLETED and Path(job.dataset.path).exists()


# ------------------------------------------------------------------ restarts
def test_download_interrupted_by_closing_the_app_comes_back_paused(env):
    make, data, tmp_path = env
    data.gate = threading.Event()
    service = make()
    job = service.start_download(_form(tmp_path))
    _wait(service, job, JOB_RUNNING)
    service.shutdown(timeout=2)

    data.gate.set()
    restarted = make()
    restored = restarted.get_progress(job)
    assert restored.status == JOB_PAUSED and restored.request.dataset == "sentinel2_sr"

    done = _wait(restarted, restarted.resume(restored), JOB_COMPLETED)
    assert _strip_values(done) == [1, 2]


def test_finished_downloads_are_listed_after_a_restart(env):
    make, _, tmp_path = env
    service = make()
    job = _wait(service, service.start_download(_form(tmp_path)), JOB_COMPLETED)
    service.shutdown(timeout=2)

    listed = make().list_jobs()
    assert [j.id for j in listed] == [job.id] and listed[0].status == JOB_COMPLETED


# ------------------------------------------------------------------ settings and access
def test_chunk_size_can_be_changed_for_the_next_download(env):
    make, _, tmp_path = env
    service = make()
    assert service.chunk_size_mb() == 1
    assert service.set_chunk_size_mb(500) == 500
    job = service.start_download(_form(tmp_path))
    assert job.total_chunks == 1


def test_gee_access_comes_from_the_data_facade(env):
    make, data, _ = env
    service = make()
    data.gee_ok = False
    assert service.is_gee_available() is False


def test_gee_checks_and_sign_in_come_from_the_data_facade(env):
    make, data, _ = env
    service = make()
    data.diagnose_gee = MagicMock(return_value=["checks"])
    data.begin_gee_sign_in = MagicMock(return_value="https://accounts.google.com/")
    data.complete_gee_sign_in = MagicMock(return_value="credentials")
    data.cancel_gee_sign_in = MagicMock()
    stop = MagicMock()

    assert service.check_gee_setup() == ["checks"]
    assert service.begin_gee_sign_in() == "https://accounts.google.com/"
    assert service.complete_gee_sign_in(stop) == "credentials"
    data.complete_gee_sign_in.assert_called_once_with(stop)
    service.cancel_gee_sign_in()
    data.cancel_gee_sign_in.assert_called_once_with()


def test_folder_name_uses_the_satellite_and_aoi_centre(tmp_path):
    form = _form(tmp_path, dataset="landsat8_l2")
    assert dataset_folder_name(form) == "Landsat-8_73.0250_31.0250"


def test_folder_name_ends_with_the_request_dates(tmp_path):
    form = _form(tmp_path, start_date=date(2023, 1, 1), end_date=date(2023, 12, 31))
    assert dataset_folder_name(form) == "Sentinel-2_73.0250_31.0250_2023-01-01_2023-12-31"
    assert dataset_folder_name(_form(tmp_path, start_date=date(2023, 1, 1))) == "Sentinel-2_73.0250_31.0250_2023-01-01"
