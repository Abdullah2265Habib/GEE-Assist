"""Download commands: start, list, show, watch, speed, pause, resume, cancel, retry, open, chunk-size.

``download watch`` redraws a progress bar, the speed (now, average, peak), the ETA,
the chunks and a speed sparkline twice a second. ``download speed`` draws the live
speed as a chart, like Task Manager. Both stop watching with Ctrl+C; the download
itself keeps going.

A download is named by its number in ``download list``, by the start of its id (at
least four characters, as with git), or by ``last`` / ``running``. Without a name,
commands use the running download, else the latest unfinished one.
"""

from __future__ import annotations

from typing import Generator, Optional, Sequence

from backend.config.download_settings import MAX_CHUNK_SIZE_MB, MIN_CHUNK_SIZE_MB
from backend.dto import DownloadJobDTO
from backend.dto.download_dto import (
    ACTIVE_JOB_STATES,
    JOB_CANCELLED,
    JOB_COMPLETED,
    JOB_FAILED,
    JOB_PAUSED,
    JOB_QUEUED,
    JOB_RUNNING,
)
from frontend.download_format import format_eta, format_size, format_speed, format_when
from frontend.gkonsol import text
from frontend.gkonsol.command import Command, Registry
from frontend.gkonsol.commands.common import YES, confirm, to_int
from frontend.gkonsol.commands.requests import find_request
from frontend.gkonsol.effects import Interrupted, Sleep, task
from frontend.gkonsol.parser import Args, Option, UsageError
from frontend.gkonsol.ports import Context
from frontend.gkonsol.text import Line, Span

GROUP = "Downloads"
REFRESH_SECONDS = 0.5
SPEED_SAMPLES = 240        # two minutes of speed, at two samples a second
CHART_HEIGHT = 6
SHORT_ID = 8
MIN_ID_PREFIX = 4

STATUS_STYLES = {
    JOB_RUNNING: text.ACCENT, JOB_QUEUED: text.INFO, JOB_PAUSED: text.WARNING,
    JOB_FAILED: text.ERROR, JOB_COMPLETED: text.SUCCESS, JOB_CANCELLED: text.MUTED,
}


# ----------------------------------------------------------------------------- finding downloads
def _jobs(ctx: Context, cancelled: bool = False) -> list[DownloadJobDTO]:
    jobs = [job for job in ctx.facade.list_downloads() if cancelled or job.status != JOB_CANCELLED]
    return sorted(jobs, key=lambda job: job.created_at)


def find_job(ctx: Context, word: Optional[str]) -> DownloadJobDTO:
    jobs = _jobs(ctx, cancelled=True)
    numbered = [job for job in jobs if job.status != JOB_CANCELLED]
    if not jobs:
        raise UsageError("There are no downloads yet. 'download start' starts one.")
    key = (word or "").lower().lstrip("#")
    if key in ("", "running", "active", "current"):
        running = [job for job in jobs if job.status == JOB_RUNNING]
        if running:
            return running[0]
        if key:
            raise UsageError("No download is running.")
        unfinished = [job for job in jobs if job.status in ACTIVE_JOB_STATES]
        return (unfinished or numbered or jobs)[-1]
    if key in ("last", "latest"):
        return (numbered or jobs)[-1]
    if key.isdigit() and len(key) <= 3:
        number = int(key)
        if 1 <= number <= len(numbered):
            return numbered[number - 1]
        raise UsageError(f"There is no download #{number}: 'download list' numbers them.")
    if len(key) < MIN_ID_PREFIX:
        raise UsageError(f"Type at least {MIN_ID_PREFIX} characters of the download's id.")
    matches = [job for job in jobs if job.id.startswith(key)]
    if len(matches) > 1:
        raise UsageError(f"'{word}' matches {len(matches)} downloads: type more of the id.")
    if not matches:
        raise UsageError(f"There is no download '{word}'. 'download list' shows them.")
    return matches[0]


def _complete_job(ctx: Context, typed: list[str], prefix: str) -> list[str]:
    return [job.id[:SHORT_ID] for job in _jobs(ctx)] if not typed else []


def _status(job: DownloadJobDTO) -> Span:
    return Span(job.status, STATUS_STYLES.get(job.status, text.TEXT))


# ----------------------------------------------------------------------------- drawings
def progress_lines(job: DownloadJobDTO, speeds: Sequence[float], peak: float, columns: int) -> list[Line]:
    """The live progress of a download: name, bar, speeds, ETA, chunks and a speed sparkline."""
    width = max(10, min(60, columns - 34))
    filled, empty = text.progress_bar(job.progress, width)
    bar_style = text.WARNING if job.status == JOB_PAUSED else text.ERROR if job.status == JOB_FAILED else text.ACCENT
    lines: list[Line] = [
        [Span("⇣ ", text.ACCENT), Span(text.truncate(job.name, max(10, columns - 16)), text.BOLD), Span("  "),
         Span(job.status.upper(), STATUS_STYLES.get(job.status, text.TEXT))],
        [Span("  "), Span(filled, bar_style), Span(empty, text.MUTED),
         Span(f"  {job.progress * 100:5.1f}%  "),
         Span(f"{format_size(job.downloaded_bytes)} / {format_size(job.total_bytes)}", text.INFO)],
    ]
    if job.status == JOB_RUNNING:
        lines.append([Span("  speed ", text.MUTED), Span(format_speed(job.speed_bps), text.ACCENT),
                      Span("  ·  average ", text.MUTED), Span(format_speed(job.average_speed_bps)),
                      Span("  ·  peak ", text.MUTED), Span(format_speed(peak)),
                      Span("  ·  ETA ", text.MUTED), Span(format_eta(job.eta_seconds), text.INFO)])
    lines.append([Span(f"  chunks {job.completed_chunks} / {job.total_chunks}", text.MUTED),
                  Span(f"  ·  received {format_size(job.received_bytes)}", text.MUTED),
                  Span(f"  ·  on disk {format_size(job.disk_bytes)}", text.MUTED),
                  Span(f"  ·  merging {format_speed(job.merge_speed_bps)}" if job.merge_speed_bps else "", text.MUTED)])
    if job.status == JOB_RUNNING and speeds:
        seconds = len(speeds[-width:]) * REFRESH_SECONDS
        lines.append([Span("  speed ", text.MUTED), Span(text.sparkline(speeds, width, top=peak or None), text.INFO),
                      Span(f"  last {seconds:.0f} s", text.MUTED)])
    note = {
        JOB_QUEUED: "Waiting for the download ahead of it to finish.",
        JOB_PAUSED: f"Paused: 'download resume {job.id[:SHORT_ID]}' continues it.",
        JOB_FAILED: job.error or "A chunk failed.",
    }.get(job.status)
    if note:
        lines.append([Span("  " + note, text.ERROR if job.status == JOB_FAILED else text.MUTED)])
    return lines


def speed_chart_lines(name: str, speeds: Sequence[float], peak: float, average: float, columns: int) -> list[Line]:
    """The speed of the last minutes as a bar chart, newest on the right."""
    label_width = 11
    width = max(10, columns - label_width - 2)
    shown = list(speeds)[-width:]
    shown = [0.0] * (width - len(shown)) + shown  # the chart fills up from the right
    top = max(peak, 1.0)
    rows = text.bar_chart(shown, CHART_HEIGHT, top=top)
    lines: list[Line] = [[Span("Download speed", text.HEADING), Span(f"  {name}", text.MUTED)]]
    for index, row in enumerate(rows):
        label = format_speed(top) if index == 0 and peak > 0 else ""
        lines.append([Span(label.rjust(label_width - 1) + " ┤" if index == 0 else " " * label_width + "│", text.MUTED),
                      Span(row, text.ACCENT)])
    lines.append([Span("0 B/s".rjust(label_width - 1) + " ┼" + "─" * width, text.MUTED)])
    ago = f"{width * REFRESH_SECONDS:.0f} s ago"
    lines.append([Span(" " * (label_width + 1) + ago + "now".rjust(max(4, width - len(ago))), text.MUTED)])
    now = speeds[-1] if speeds else 0.0
    lines.append([Span("  now ", text.MUTED), Span(format_speed(now), text.ACCENT),
                  Span("  ·  average ", text.MUTED), Span(format_speed(average)),
                  Span("  ·  peak ", text.MUTED), Span(format_speed(peak)),
                  Span("    Ctrl+C stops", text.MUTED)])
    return lines


# ----------------------------------------------------------------------------- following progress
def follow(ctx: Context, job: DownloadJobDTO) -> Generator:
    """Redraw ``job``'s progress until it stops running (or Ctrl+C)."""
    ctx.out.muted("Ctrl+C stops watching; the download keeps going.")
    speeds: list[float] = []
    peak = 0.0
    live = ctx.out.live()
    try:
        while True:
            job = ctx.facade.get_download_progress(job)
            if job.status == JOB_RUNNING:
                speeds.append(job.speed_bps)
                del speeds[:-SPEED_SAMPLES]
                peak = max(peak, job.speed_bps)
            live.update(progress_lines(job, speeds, peak, ctx.out.columns))
            if job.status not in (JOB_RUNNING, JOB_QUEUED):
                break
            yield Sleep(REFRESH_SECONDS)
    except Interrupted:
        live.done()
        ctx.out.muted(f"Stopped watching. The download goes on: 'download watch {job.id[:SHORT_ID]}' follows it again.")
        return
    live.done()
    _outcome(ctx, job)


def _outcome(ctx: Context, job: DownloadJobDTO) -> None:
    short = job.id[:SHORT_ID]
    if job.status == JOB_COMPLETED:
        where = job.dataset.path if job.dataset else job.folder
        ctx.out.success(f"Download complete: {where}  ({format_size(job.total_bytes)})")
        ctx.out.hint(f"download open {short}  opens its folder")
    elif job.status == JOB_PAUSED:
        ctx.out.warning(f"Paused at {job.progress * 100:.1f}%. 'download resume {short}' continues it.")
    elif job.status == JOB_FAILED:
        ctx.out.error(f"Download failed: {job.error or 'a chunk could not be fetched.'}")
        ctx.out.hint(f"download retry {short}  fetches the failed chunks again")
    elif job.status == JOB_CANCELLED:
        ctx.out.muted("Cancelled: its files were deleted.")


def start(ctx: Context, request: Optional[str], detach: bool) -> Generator:
    number, form = find_request(ctx, request)
    job = yield task(ctx.facade.start_download, form, label="Preparing the download")
    ctx.out.success(f"Download started: {job.name}")
    ctx.out.pairs([
        ("Id", Span(job.id, text.ACCENT)),
        ("Request", f"#{number}"),
        ("Size", f"about {format_size(job.total_bytes)} in {job.total_chunks} chunk{'s' if job.total_chunks != 1 else ''}"),
        ("Folder", job.folder),
    ])
    if detach:
        ctx.out.hint(f"download watch {job.id[:SHORT_ID]}  follows its progress")
        return
    yield from follow(ctx, job)


# ----------------------------------------------------------------------------- commands
def _start(ctx: Context, args: Args) -> Generator:
    yield from start(ctx, args.word(0), args.flag("detach"))


def _list(ctx: Context, args: Args) -> None:
    jobs = _jobs(ctx, cancelled=args.flag("all"))
    if not jobs:
        ctx.out.muted("No downloads yet. 'download start' downloads the latest kept request.")
        return
    numbers = {job.id: number for number, job in enumerate(_jobs(ctx), start=1)}
    rows = []
    for job in jobs:
        filled, empty = text.progress_bar(job.progress, 10)
        speed = format_speed(job.speed_bps) if job.status == JOB_RUNNING else "—"
        eta = format_eta(job.eta_seconds) if job.status == JOB_RUNNING else "—"
        rows.append([f"#{numbers[job.id]}" if job.id in numbers else "", job.id[:SHORT_ID], job.name, _status(job),
                     f"{filled}{empty} {job.progress * 100:5.1f}%",
                     f"{format_size(job.downloaded_bytes)} / {format_size(job.total_bytes)}", speed, eta])
    ctx.out.table(["#", "ID", "NAME", "STATUS", "PROGRESS", "SIZE", "SPEED", "ETA"], rows, align="llllllrr",
                  styles=(text.ACCENT, text.MUTED))
    ctx.out.muted("'download show <# or id>' for details  ·  'download watch' follows the running one")


def _show(ctx: Context, args: Args) -> None:
    job = find_job(ctx, args.word(0))
    ctx.out.print(Span(job.name, text.HEADING), "  ", _status(job))
    pairs = [
        ("Id", job.id),
        ("Folder", job.folder),
        ("Progress", f"{job.progress * 100:.1f}%  ({format_size(job.downloaded_bytes)} of {format_size(job.total_bytes)})"),
        ("Chunks", f"{job.completed_chunks} of {job.total_chunks} merged"),
        ("Received", f"{format_size(job.received_bytes)} from Earth Engine"),
        ("Merged file", f"{format_size(job.merged_bytes)}  {job.merged_path}" if job.merged_path else "—"),
        ("Started", format_when(job.created_at) or "—"),
    ]
    if job.status == JOB_RUNNING:
        pairs += [("Speed", f"{format_speed(job.speed_bps)} now, {format_speed(job.average_speed_bps)} on average"),
                  ("Time left", format_eta(job.eta_seconds))]
    if job.finished_at:
        pairs.append(("Finished", format_when(job.finished_at)))
    if job.dataset is not None:
        pairs.append(("Result", Span(job.dataset.path, text.SUCCESS)))
    if job.error:
        pairs.append(("Error", Span(job.error, text.ERROR)))
    ctx.out.pairs(pairs)
    if job.chunks:
        ctx.out.blank()
        ctx.out.table(["CHUNK", "STATUS", "SIZE", "DOWNLOADED", "RETRIES"],
                      [[f"{chunk.id}", chunk.status, format_size(chunk.size_bytes), format_size(chunk.downloaded_bytes),
                        str(chunk.retries)] for chunk in job.chunks], align="rllrr")


def _watch(ctx: Context, args: Args) -> Generator:
    yield from follow(ctx, find_job(ctx, args.word(0)))


def _speed(ctx: Context, args: Args) -> Generator:
    job = find_job(ctx, args.word(0)) if args.word(0) else None
    speeds: list[float] = []
    peak = 0.0
    live = ctx.out.live()
    try:
        while True:
            if job is not None:
                job = ctx.facade.get_download_progress(job)
                current = job
            else:  # whatever is running, like Task Manager
                current = next((j for j in ctx.facade.list_downloads() if j.status == JOB_RUNNING), None)
            speed = current.speed_bps if current is not None and current.status == JOB_RUNNING else 0.0
            speeds.append(speed)
            del speeds[:-SPEED_SAMPLES]
            peak = max(peak, speed)
            name = current.name if current is not None else "no download is running"
            average = current.average_speed_bps if current is not None else 0.0
            live.update(speed_chart_lines(name, speeds, peak, average, ctx.out.columns))
            if job is not None and job.status not in (JOB_RUNNING, JOB_QUEUED):
                break
            yield Sleep(REFRESH_SECONDS)
    except Interrupted:
        live.done()
        return
    live.done()
    _outcome(ctx, job)


def _pause(ctx: Context, args: Args) -> None:
    job = find_job(ctx, args.word(0))
    if job.status not in (JOB_RUNNING, JOB_QUEUED):
        ctx.out.muted(f"{job.name} is {job.status}: there is nothing to pause.")
        return
    job = ctx.facade.pause_download(job)
    ctx.out.success(f"Paused {job.name}. Finished parts are kept; 'download resume {job.id[:SHORT_ID]}' continues it.")


def _resume(ctx: Context, args: Args) -> Generator:
    job = find_job(ctx, args.word(0))
    if job.status not in (JOB_PAUSED, JOB_FAILED):
        ctx.out.muted(f"{job.name} is {job.status}: there is nothing to resume.")
        return
    job = ctx.facade.resume_download(job)
    ctx.out.success(f"Resumed {job.name} ({job.status}).")
    if not args.flag("detach"):
        yield from follow(ctx, job)


def _retry(ctx: Context, args: Args) -> Generator:
    job = find_job(ctx, args.word(0))
    if job.status != JOB_FAILED:
        ctx.out.muted(f"{job.name} is {job.status}: only a failed download is retried.")
        return
    job = ctx.facade.retry_failed_chunks(job)
    ctx.out.success(f"Retrying the failed chunks of {job.name}.")
    if not args.flag("detach"):
        yield from follow(ctx, job)


def _cancel(ctx: Context, args: Args) -> Generator:
    job = find_job(ctx, args.word(0))
    if job.is_finished:
        ctx.out.muted(f"{job.name} is {job.status}: there is nothing to cancel.")
        return
    if not (yield from confirm(f"Cancel downloading {job.name}? The files downloaded so far are deleted.",
                               args.flag("yes"))):
        ctx.out.muted("The download goes on.")
        return
    job = yield task(ctx.facade.cancel_download, job, label="Cancelling and deleting the files")
    ctx.out.success(f"Cancelled {job.name}; its files are deleted.")


def _open(ctx: Context, args: Args) -> None:
    job = find_job(ctx, args.word(0))
    if job.status == JOB_CANCELLED:
        raise UsageError(f"{job.name} was cancelled: its folder is gone.")
    if not ctx.app.open_path(job.folder):
        raise UsageError(f"Could not open {job.folder}.")
    ctx.out.muted(f"Opened {job.folder}")


def _chunk_size(ctx: Context, args: Args) -> None:
    if args.word(0) is None:
        ctx.out.print("New downloads are split into ", Span(f"{ctx.facade.get_chunk_size_mb()} MB", text.ACCENT),
                      " chunks.")
        ctx.out.hint(f"download chunk-size <MB>  changes it ({MIN_CHUNK_SIZE_MB}-{MAX_CHUNK_SIZE_MB})")
        return
    size = to_int(args.words[0].upper().removesuffix("MB"), "The chunk size (MB)", MIN_CHUNK_SIZE_MB, MAX_CHUNK_SIZE_MB)
    saved = ctx.facade.set_chunk_size_mb(size)
    ctx.out.success(f"New downloads will use {saved} MB chunks. Running downloads keep theirs.")


def register(registry: Registry) -> None:
    detach = Option("detach", "Do not follow the progress; return to the prompt", short="d")
    job_param = "[DOWNLOAD]"
    download = registry.add(Command(
        "download", "Download datasets from Earth Engine and follow them", _list, aliases=("dl", "downloads"),
        group=GROUP, options=[Option("all", "Also list cancelled downloads", short="a")],
        description="'download' alone is 'download list'. DOWNLOAD is a number from 'download list', the start of\n"
                    "an id (4+ characters), 'last' or 'running'; without it, the running download is used.",
    ))
    download.add(Command(
        "start", "Download a kept request and follow its progress", _start, params="[REQUEST]", max_args=1,
        options=[detach], completer=lambda ctx, typed, prefix: [str(n) for n in range(1, len(ctx.facade.get_kept_requests()) + 1)],
        description="REQUEST is the number of a kept request ('requests list'); without it, the latest one.\n"
                    "The progress bar, speed and ETA are redrawn live until the download ends; Ctrl+C stops\n"
                    "watching but not the download.",
        examples=[("download start", "The latest kept request"), ("download start 2 -d", "Request #2, in the background")],
    ))
    download.add(Command(
        "list", "List the downloads with their progress, speed and ETA", _list, aliases=("ls",),
        options=[Option("all", "Also list cancelled downloads", short="a")],
    ))
    download.add(Command("show", "Show a download's details and chunks", _show, params=job_param, max_args=1,
                         aliases=("info",), completer=_complete_job))
    download.add(Command(
        "watch", "Follow a download live: progress bar, speed and ETA", _watch, params=job_param, max_args=1,
        aliases=("progress", "follow"), completer=_complete_job,
        examples=[("download watch", "The running download"), ("download watch 3f9a", "By the start of its id")],
    ))
    download.add(Command(
        "speed", "Show the live download speed as a chart", _speed, params=job_param, max_args=1,
        completer=_complete_job,
        description="Without DOWNLOAD it shows whatever is downloading, until Ctrl+C; with one, until it ends.",
    ))
    download.add(Command("pause", "Pause a download (finished parts are kept)", _pause, params=job_param,
                         max_args=1, completer=_complete_job))
    download.add(Command("resume", "Continue a paused (or failed) download", _resume, params=job_param, max_args=1,
                         aliases=("continue",), options=[detach], completer=_complete_job))
    download.add(Command("retry", "Fetch the failed chunks of a download again", _retry, params=job_param,
                         max_args=1, options=[detach], completer=_complete_job))
    download.add(Command("cancel", "Cancel a download and delete its files", _cancel, params=job_param, max_args=1,
                         options=[YES], completer=_complete_job))
    download.add(Command("open", "Open a download's folder", _open, params=job_param, max_args=1,
                         completer=_complete_job))
    download.add(Command(
        "chunk-size", "Show or change the chunk size of new downloads", _chunk_size, params="[MB]", max_args=1,
        examples=[("download chunk-size", "The current size"), ("download chunk-size 250", "250 MB chunks")],
    ))
