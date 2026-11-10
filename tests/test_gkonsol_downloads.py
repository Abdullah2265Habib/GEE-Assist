"""gkonsol's kept-request and download commands, with the live progress bar and speed chart."""

import json
from datetime import date

import pytest

from backend.dto import ChunkDTO, DatasetDTO, DownloadJobDTO, FormDTO
from backend.exceptions import ValidationError
from frontend.gkonsol.parser import UsageError
from frontend.gkonsol import text
from frontend.gkonsol.commands import downloads
from tests.gkonsol_fakes import terminal

SQUARE = json.dumps({"type": "Polygon", "coordinates": [[[73, 31], [73.1, 31], [73.1, 31.1], [73, 31.1], [73, 31]]]})
GB = 1_000_000_000


def _form(**extra) -> FormDTO:
    values = dict(dataset="sentinel2_sr", bands=["B4", "B8"], scale=10, aoi=SQUARE, aoi_name="Faisalabad",
                  start_date=date(2024, 6, 1), end_date=date(2024, 8, 31), source="form")
    values.update(extra)
    return FormDTO(**values)


def _job(job_id="3f9a1c2b7d4e", status="running", created="2026-11-10T10:00:00", **extra) -> DownloadJobDTO:
    chunks = [ChunkDTO(n, (0, 0, 1, 1), "EPSG:4326", (1, 0, 0, 0, -1, 1), 1, 1, n - 1, ["B4", "B8"],
                       size_bytes=GB // 2, status="merged" if n == 1 else "downloading") for n in (1, 2)]
    values = dict(total_chunks=2, completed_chunks=1, chunks=chunks, total_bytes=GB, downloaded_bytes=GB // 2,
                  received_bytes=GB // 2, disk_bytes=GB // 2, speed_bps=4_200_000, average_speed_bps=3_900_000,
                  eta_seconds=221, request=_form(), created_at=created)
    values.update(extra)
    return DownloadJobDTO(job_id, f"Sentinel-2_73.0500_31.0500_{job_id[:4]}", f"D:/downloads/{job_id}", status=status,
                          **values)


@pytest.fixture
def term():
    return terminal()


def _progress(term, *states):
    """get_download_progress returns these states one after another (the last one stays)."""
    queue = list(states)
    term.facade.get_download_progress.side_effect = lambda job: queue.pop(0) if len(queue) > 1 else queue[0]


# ------------------------------------------------------------------ kept requests
def test_requests_list(term):
    term.facade.get_kept_requests.return_value = [_form(), FormDTO(source="nl", query_text="NDVI of Lahore")]
    printed = term.type("requests")
    assert "#1" in printed and "sentinel2_sr · download only" in printed and "Faisalabad" in printed
    assert "NDVI of Lahore" in printed and "yes" in printed and "no" in printed


def test_requests_when_none_are_kept(term):
    assert "No requests are kept yet" in term.type("requests list")
    assert "No requests are kept yet" in term.type("download start")


def test_requests_show(term):
    term.facade.get_kept_requests.return_value = [_form()]
    printed = term.type("requests show 1")
    assert "Request #1" in printed and "sentinel2_sr" in printed and "download start 1" in printed
    assert "from 1 to 1" in term.type("requests show 5")


# ------------------------------------------------------------------ start and follow
def test_start_follows_the_progress_until_it_completes(term):
    term.facade.get_kept_requests.return_value = [_form(), _form(dataset="landsat8_l2")]
    started = _job(status="queued", downloaded_bytes=0, speed_bps=0)
    term.facade.start_download.return_value = started
    done = _job(status="completed", downloaded_bytes=GB, completed_chunks=2, speed_bps=0,
                dataset=DatasetDTO("x", "S2", "D:/downloads/x/x.tif", size_bytes=GB))
    _progress(term, _job(), _job(downloaded_bytes=GB * 3 // 4, speed_bps=6_000_000), done)

    printed = term.type("download start")
    assert term.facade.start_download.call_args.args[0].dataset == "landsat8_l2"  # the latest request
    assert "✓ Download started: Sentinel-2_73.0500_31.0500_3f9a" in printed and "#2" in printed
    assert "Ctrl+C stops watching" in printed
    assert "✓ Download complete: D:/downloads/x/x.tif  (1.0 GB)" in printed and "download open 3f9a1c2b" in printed
    assert "100.0%" in printed and term.sink.live == [] and term.shell.running is None


def test_start_a_given_request_in_the_background(term):
    term.facade.get_kept_requests.return_value = [_form(), _form(dataset="landsat8_l2")]
    term.facade.start_download.return_value = _job(status="queued")
    printed = term.type("download start 1 --detach")
    assert term.facade.start_download.call_args.args[0].dataset == "sentinel2_sr"
    assert "download watch 3f9a1c2b" in printed
    term.facade.get_download_progress.assert_not_called()


def test_start_reports_backend_errors(term):
    term.facade.get_kept_requests.return_value = [_form()]
    term.facade.start_download.side_effect = ValidationError("Choose an area of interest before downloading.")
    assert "✗ Choose an area of interest before downloading." in term.type("download start")


def test_live_progress_is_redrawn_in_place(term):
    term.facade.list_downloads.return_value = [_job()]
    _progress(term, _job(downloaded_bytes=GB // 4), _job(downloaded_bytes=GB // 2))
    term.type("download watch", settle=False)
    first = term.sink.text()
    assert "25.0%" in first and "RUNNING" in first and "speed 4.2 MB/s" in first and "ETA 03:41" in first
    term.scheduler.fire_timers()
    redrawn = term.sink.text()
    assert "50.0%" in redrawn and "25.0%" not in redrawn  # the same lines, redrawn
    assert term.shell.status() == "download watch is running  (Ctrl+C to stop)"
    term.shell.interrupt()
    assert "Stopped watching. The download goes on: 'download watch 3f9a1c2b'" in term.output()
    assert term.shell.running is None


def test_watching_a_paused_download_ends_at_once(term):
    paused = _job(status="paused", speed_bps=0)
    term.facade.list_downloads.return_value = [paused]
    _progress(term, paused)
    printed = term.type("download watch")
    assert "PAUSED" in printed and "! Paused at 50.0%. 'download resume 3f9a1c2b' continues it." in printed


def test_a_failed_download_says_how_to_retry(term):
    failed = _job(status="failed", error="Chunk 2 failed 3 times: Earth Engine is busy.")
    term.facade.list_downloads.return_value = [failed]
    _progress(term, failed)
    printed = term.type("download watch 1")
    assert "Download failed: Chunk 2 failed 3 times" in printed and "download retry 3f9a1c2b" in printed


# ------------------------------------------------------------------ list, show, finding downloads
@pytest.fixture
def jobs(term):
    listed = [
        _job("aaaa11112222", "completed", "2026-11-09T09:00:00", finished_at="2026-11-09T09:30:00"),
        _job("bbbb33334444", "running", "2026-11-10T10:00:00"),
        _job("bbbc55556666", "paused", "2026-11-10T11:00:00"),
        _job("cccc77778888", "cancelled", "2026-11-10T12:00:00"),
    ]
    term.facade.list_downloads.return_value = listed
    return listed


def test_list_numbers_the_downloads(term, jobs):
    printed = term.type("download")
    lines = printed.split("\n")
    assert lines[1].split()[:2] == ["#", "ID"]
    assert "#1" in lines[2] and "aaaa1111" in lines[2] and "completed" in lines[2]
    assert "#2" in lines[3] and "running" in lines[3] and "4.2 MB/s" in lines[3] and "03:41" in lines[3]
    assert "cccc7777" not in printed  # cancelled ones only with --all
    assert "cccc7777" in term.type("download list --all")


@pytest.mark.parametrize("word, job_id", [
    (None, "bbbb33334444"), ("2", "bbbb33334444"), ("#3", "bbbc55556666"), ("aaaa", "aaaa11112222"),
    ("bbbb3", "bbbb33334444"), ("bbbc", "bbbc55556666"), ("last", "bbbc55556666"), ("running", "bbbb33334444"),
])
def test_downloads_are_found_by_number_id_or_name(term, jobs, word, job_id):
    assert downloads.find_job(term.shell.context, word).id == job_id


@pytest.mark.parametrize("word, message", [
    ("bbb", "at least 4 characters"), ("9", "no download #9"), ("dddd", "no download 'dddd'"),
])
def test_unclear_download_names_are_explained(term, jobs, word, message):
    with pytest.raises(UsageError, match=message):
        downloads.find_job(term.shell.context, word)


def test_ambiguous_ids(term, jobs):
    jobs.append(_job("bbbb3333ffff", "paused", "2026-11-10T13:00:00"))
    with pytest.raises(UsageError, match="matches 2 downloads"):
        downloads.find_job(term.shell.context, "bbbb3333")


def test_no_downloads_at_all(term):
    with pytest.raises(UsageError, match="no downloads yet"):
        downloads.find_job(term.shell.context, None)


def test_show_lists_the_details_and_chunks(term, jobs):
    printed = term.type("download show aaaa")
    assert "Sentinel-2_73.0500_31.0500_aaaa  completed" in printed
    assert "CHUNK" in printed and "merged" in printed and "Finished" in printed


def test_completion_offers_short_ids(term, jobs):
    assert term.shell.complete("download watch b")[1] == ["bbbb3333", "bbbc5555"]


# ------------------------------------------------------------------ control
def test_pause_and_resume(term, jobs):
    term.facade.pause_download.return_value = _job("bbbb33334444", "paused")
    assert "Paused Sentinel-2_73.0500_31.0500_bbbb" in term.type("download pause")
    term.facade.resume_download.return_value = _job("bbbc55556666", "queued")
    assert "Resumed Sentinel-2_73.0500_31.0500_bbbc (queued)." in term.type("download resume 3 -d")
    assert "nothing to resume" in term.type("download resume 1")
    assert "nothing to pause" in term.type("download pause aaaa")


def test_retry_only_failed_downloads(term, jobs):
    assert "only a failed download is retried" in term.type("download retry 2")
    jobs.append(_job("dddd99990000", "failed", "2026-11-10T14:00:00"))
    term.facade.retry_failed_chunks.return_value = _job("dddd99990000", "queued")
    assert "Retrying the failed chunks" in term.type("download retry dddd -d")


def test_cancel_asks_then_deletes(term, jobs):
    term.facade.cancel_download.return_value = _job("bbbc55556666", "cancelled")
    term.type("download cancel 3")
    assert "files downloaded so far are deleted" in term.shell.runner.asking.prompt
    assert "The download goes on." in term.type("n")
    term.facade.cancel_download.assert_not_called()
    assert "Cancelled Sentinel-2_73.0500_31.0500_bbbc; its files are deleted." in term.type("download cancel 3 -y")


def test_open_the_folder(term, jobs):
    term.type("download open 1")
    assert ("open_path", "D:/downloads/aaaa11112222") in term.app.calls


def test_chunk_size(term):
    assert "500 MB" in term.type("download chunk-size")
    term.facade.set_chunk_size_mb.return_value = 250
    assert "New downloads will use 250 MB chunks." in term.type("download chunk-size 250MB")
    term.facade.set_chunk_size_mb.assert_called_once_with(250)
    assert "from 1 to 102400" in term.type("download chunk-size 0")


# ------------------------------------------------------------------ speed chart
def test_speed_chart_follows_whatever_is_running_until_ctrl_c(term, jobs):
    term.type("download speed", settle=False)
    for _ in range(3):
        term.scheduler.fire_timers()
    chart = term.sink.text()
    assert "Download speed  Sentinel-2_73.0500_31.0500_bbbb" in chart
    assert "4.2 MB/s ┤" in chart and "0 B/s ┼" in chart and "now 4.2 MB/s" in chart and "█" in chart
    term.shell.interrupt()
    assert term.shell.running is None


def test_speed_chart_without_a_download(term):
    term.type("download speed", settle=False)
    assert "no download is running" in term.sink.text() and "now 0 B/s" in term.sink.text()
    term.shell.interrupt()


# ------------------------------------------------------------------ drawings
def test_progress_lines_for_each_state():
    running = [text.plain(line) for line in downloads.progress_lines(_job(), [1e6, 4.2e6], 4.2e6, 100)]
    assert running[0].startswith("⇣ Sentinel-2") and running[0].endswith("RUNNING")
    assert " 50.0%  500.0 MB / 1.0 GB" in running[1] and "█" in running[1] and "░" in running[1]
    assert "speed 4.2 MB/s  ·  average 3.9 MB/s  ·  peak 4.2 MB/s  ·  ETA 03:41" == running[2].strip()
    assert running[3].strip().startswith("chunks 1 / 2") and running[4].strip().endswith("last 1 s")
    queued = [text.plain(line) for line in downloads.progress_lines(_job(status="queued"), [], 0, 100)]
    assert queued[-1].strip() == "Waiting for the download ahead of it to finish." and "speed" not in queued[2]


def test_progress_lines_fit_narrow_terminals():
    lines = downloads.progress_lines(_job(), [1e6], 1e6, 40)
    assert all(len(text.plain(line)) <= 70 for line in lines)


def test_speed_chart_lines_line_up():
    lines = [text.plain(line) for line in downloads.speed_chart_lines("job", [0, 1e6, 2e6, 4e6], 4e6, 2e6, 60)]
    chart = lines[1:1 + downloads.CHART_HEIGHT + 1]
    assert len({len(line) for line in chart}) == 1  # the axis and every row are as wide
    assert lines[1].lstrip().startswith("4.0 MB/s ┤") and lines[-1].strip().startswith("now 4.0 MB/s")
