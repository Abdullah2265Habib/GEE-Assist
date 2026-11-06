"""Downloads page, Start Download in Kept Requests, and the display helpers (no window on screen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

from backend.business.facade import IBusinessFacade  # noqa: E402
from backend.dto import ChunkDTO, DatasetDTO, DownloadJobDTO, FormDTO  # noqa: E402
from backend.exceptions import ValidationError  # noqa: E402
from frontend.download_format import format_eta, format_size, format_speed, format_when  # noqa: E402
from frontend.views import download_view as download_module  # noqa: E402
from frontend.views.download_view import DownloadView  # noqa: E402
from frontend.views.kept_requests_view import KeptRequestsView  # noqa: E402
from frontend.widgets.download_rows import CompletedRow, JobRow, job_status, job_title  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _job(job_id: str, status: str, **extra) -> DownloadJobDTO:
    form = FormDTO(dataset="sentinel2_sr", aoi_name="Faisalabad AOI", start_date=date(2024, 6, 1), end_date=date(2024, 8, 31))
    chunks = [ChunkDTO(n, (0, 0, 1, 1), "EPSG:4326", (1, 0, 0, 0, -1, 1), 1, 1, n - 1, ["B4", "B8"], size_bytes=500_000_000)
              for n in (1, 2)]
    values = dict(total_chunks=2, chunks=chunks, request=form, total_bytes=1_000_000_000)
    values.update(extra)
    return DownloadJobDTO(job_id, f"Sentinel-2_73.0{job_id}_31.4", f"D:/downloads/{job_id}", status=status, **values)


@pytest.fixture
def facade():
    fake = MagicMock(spec=IBusinessFacade)
    fake.list_downloads.return_value = []
    fake.get_chunk_size_mb.return_value = 500
    fake.is_gee_available.return_value = True
    return fake


@pytest.fixture
def view(app, facade):
    page = DownloadView(facade)
    yield page
    page.deleteLater()


def _rows(section):
    return [section.rows.itemAt(i).widget() for i in range(1, section.rows.count())]


# ------------------------------------------------------------------ sections
def test_jobs_are_shown_in_their_sections(view, facade):
    facade.list_downloads.return_value = [
        _job("1", "completed", finished_at="2026-11-06T10:15:00", dataset=DatasetDTO("1", "S2", "x.tif", size_bytes=10)),
        _job("2", "queued"),
        _job("3", "running", downloaded_bytes=740_000_000, speed_bps=915_200, eta_seconds=135),
        _job("4", "paused"),
        _job("5", "failed", error="Chunk 2 failed"),
        _job("6", "cancelled"),
    ]
    view.refresh()

    assert [r.job.id for r in _rows(view.queued)] == ["3", "2"]  # the running one first
    assert [r.job.id for r in _rows(view.paused)] == ["4", "5"]
    assert [r.job.id for r in _rows(view.completed)] == ["1"]
    assert view.queued.title_label.text() == "QUEUED (2)"
    assert view.completed.title_label.text() == "COMPLETED HISTORY (1)"
    assert all(isinstance(r, JobRow) for r in _rows(view.queued)) and isinstance(_rows(view.completed)[0], CompletedRow)


def test_rows_are_reused_and_move_between_sections(view, facade):
    facade.list_downloads.return_value = [_job("1", "running")]
    view.refresh()
    row = _rows(view.queued)[0]

    facade.list_downloads.return_value = [_job("1", "running", downloaded_bytes=500_000_000)]
    view.refresh()
    assert _rows(view.queued)[0] is row and row.size.text() == "500.0 MB / 1.0 GB"

    facade.list_downloads.return_value = [_job("1", "paused")]
    view.refresh()
    assert _rows(view.queued) == [] and _rows(view.paused)[0].job.status == "paused"


def test_empty_sections_say_so(view):
    view.refresh()
    assert not view.queued.empty_label.isHidden()
    assert view.queued.title_label.text() == "QUEUED (0)"


def test_statistics_follow_the_running_download(view, facade):
    facade.list_downloads.return_value = [_job("1", "running", downloaded_bytes=740_000_000, speed_bps=1_500_000, merge_speed_bps=3_200_000)]
    view.refresh()

    assert view.stats["CURRENT"].text() == "1.5 MB/s"
    assert view.stats["PEAK"].text() == "1.5 MB/s"
    assert view.stats["DOWNLOADED"].text() == "740.0 MB"
    assert view.stats["REMAINING"].text() == "260.0 MB"
    assert view.stats["MERGING SPEED"].text() == "3.2 MB/s"
    assert view.chunk_setting.text() == "Chunk size: 500 MB"
    assert view.chart.samples()[-1] == 1_500_000


# ------------------------------------------------------------------ buttons
def test_row_buttons_match_the_job_state(app):
    running, paused, failed = JobRow(_job("1", "running")), JobRow(_job("2", "paused")), JobRow(_job("3", "failed"))

    assert not running.start_button.isEnabled() and running.pause_button.isEnabled()
    assert paused.start_button.isEnabled() and not paused.pause_button.isEnabled()
    assert failed.start_button.text() == "Retry" and failed.start_button.isEnabled()


def test_start_pause_and_retry_call_the_facade(view, facade):
    facade.list_downloads.return_value = [_job("1", "running"), _job("2", "paused"), _job("3", "failed")]
    view.refresh()
    running, paused_row, failed_row = _rows(view.queued)[0], *_rows(view.paused)

    running.pause_button.click()
    paused_row.start_button.click()
    failed_row.start_button.click()

    assert facade.pause_download.call_args[0][0].id == "1"
    assert facade.resume_download.call_args[0][0].id == "2"
    assert facade.retry_failed_chunks.call_args[0][0].id == "3"


def test_cancel_asks_before_deleting(view, facade, monkeypatch):
    calls = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    monkeypatch.setattr(download_module, "run_task", lambda owner, fn, *args, **kw: calls.append((fn, args)))
    facade.list_downloads.return_value = [_job("1", "running")]
    view.refresh()

    _rows(view.queued)[0].cancel_button.click()
    assert calls == []

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    _rows(view.queued)[0].cancel_button.click()
    assert calls[0][0] == facade.cancel_download and calls[0][1][0].id == "1"


def test_facade_errors_are_shown_in_the_banner(view, facade):
    facade.list_downloads.return_value = [_job("1", "paused")]
    facade.resume_download.side_effect = ValidationError("That download no longer exists.")
    view.refresh()

    _rows(view.paused)[0].start_button.click()
    assert view.banner.text() == "That download no longer exists."


def test_chunk_size_can_be_changed(view, facade, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getInt", lambda *a, **k: (250, True))
    facade.set_chunk_size_mb.return_value = 250

    view.change_chunk.click()
    facade.set_chunk_size_mb.assert_called_once_with(250)
    assert "250 MB" in view.banner.text()


def test_start_runs_in_the_background_and_reports_the_job(view, facade, monkeypatch):
    monkeypatch.setattr(download_module, "run_task",
                        lambda owner, fn, *args, on_success=None, on_error=None: on_success(fn(*args)))
    facade.start_download.return_value = _job("9", "queued")
    started = []
    view.download_started.connect(started.append)

    view.start(FormDTO(dataset="sentinel2_sr"))
    assert started and started[0].id == "9"
    assert "1.0 GB in 2 chunks" in view.banner.text()


# ------------------------------------------------------------------ kept requests
def _form(**overrides) -> FormDTO:
    values = dict(dataset="sentinel2_sr", aoi='{"type": "Polygon", "coordinates": []}', source="form",
                  start_date=date(2024, 6, 1), end_date=date(2024, 8, 31))
    values.update(overrides)
    return FormDTO(**values)


def test_start_download_sends_the_selected_request(app):
    kept = KeptRequestsView()
    requested = []
    kept.download_requested.connect(requested.append)
    form = _form()
    kept.set_requests([form])

    assert kept.download_button.isEnabled()
    kept.download_button.click()
    assert requested == [form]


def test_text_queries_cannot_be_downloaded_directly(app):
    kept = KeptRequestsView()
    kept.set_requests([_form(source="nl", aoi="", query_text="NDVI for Lahore")])
    assert not kept.download_button.isEnabled()


# ------------------------------------------------------------------ text
def test_titles_and_statuses(app):
    assert job_title(_job("1", "running")) == "Sentinel-2 - Faisalabad AOI"
    assert job_status(_job("1", "running", downloaded_bytes=740_000_000)) == "DOWNLOADING 74%"
    assert job_status(_job("1", "paused", downloaded_bytes=400_000_000)) == "PAUSED 40%"
    assert job_status(_job("1", "queued")) == "WAITING"
    merging = _job("1", "running")
    merging.chunks[1].status = "downloaded"
    assert job_status(merging) == "MERGING CHUNK 2"


def test_display_formats():
    assert format_size(7_800_000_000) == "7.8 GB"
    assert format_size(500_000_000) == "500.0 MB"
    assert format_speed(915_200) == "915.2 KB/s"
    assert format_eta(135) == "02:15" and format_eta(3725) == "1:02:05" and format_eta(None) == "--:--"
    today = date(2026, 11, 6)
    assert format_when("2026-11-06T10:15:00", today) == "Today 10:15 AM"
    assert format_when("2026-11-05T15:30:00", today) == "Yesterday 3:30 PM"
    assert format_when("2026-06-05T02:23:00", today) == "Jun 5, 2026 2:23 AM"
