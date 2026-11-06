"""Downloads page (UC-05 Fetch Data): live speed, statistics and every download job.

Sections:
  QUEUED             the running download and those waiting for it
  PAUSED             paused or failed downloads (Start resumes, Retry retries failed chunks)
  COMPLETED HISTORY  finished downloads; the green button opens the dataset folder

The page polls the facade twice a second, also while it is hidden, so the speed graph
keeps a continuous history (like Task Manager).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from backend.business.facade import IBusinessFacade
from backend.config.download_settings import MAX_CHUNK_SIZE_MB, MIN_CHUNK_SIZE_MB
from backend.dto import DownloadJobDTO, FormDTO
from backend.dto.download_dto import JOB_COMPLETED, JOB_FAILED, JOB_PAUSED, JOB_QUEUED, JOB_RUNNING
from backend.exceptions import GeeAssistError
from frontend import form_theme, theme
from frontend.download_format import format_size, format_speed
from frontend.widgets.download_rows import CollapsibleSection, CompletedRow, JobRow
from frontend.widgets.form_parts import StatusBanner
from frontend.widgets.speed_chart import SpeedChart
from frontend.workers.task_worker import run_task

REFRESH_MS = 500
NONE = "–"   # shown when no download is running

STYLESHEET = f"""
#DownloadPage {{ background: transparent; }}
QLabel#PageTitle {{ font-family: "{theme.SERIF}"; font-size: 20pt; color: {theme.INK}; }}
QLabel#PageSubtitle {{ color: {theme.MUTED}; }}
QFrame#StatsCard, QFrame#DownloadSection {{
    background: {theme.WHITE}; border: 1px solid {theme.BORDER}; border-radius: 12px;
}}
QFrame#StatsCard QLabel, QFrame#DownloadSection QLabel {{ background: transparent; }}
QLabel#StatName {{ color: {theme.MUTED}; font-size: 8.5pt; font-weight: 600; letter-spacing: 0.5px; }}
QLabel#StatValue {{ color: {theme.INK}; font-size: 15pt; }}
QLabel#ChunkSetting {{ color: {theme.MUTED}; font-size: 9pt; }}
QFrame#SectionHeader {{
    border: none; border-bottom: 1px solid {form_theme.HEADER_LINE};
    border-top-left-radius: 12px; border-top-right-radius: 12px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {form_theme.HEADER_GREEN}, stop:1 {form_theme.HEADER_BLUE});
}}
QLabel#SectionHeaderText {{ color: {theme.INK}; font-weight: 600; letter-spacing: 0.6px; }}
QToolButton#SectionToggle {{ border: none; background: transparent; padding: 2px; }}
QFrame#JobRow {{ border: none; border-top: 1px solid {theme.BORDER}; background: transparent; }}
QLabel#SatelliteIcon {{ font-family: "Segoe UI Emoji"; font-size: 20pt; }}
QLabel#JobTitle {{ color: {theme.INK}; font-size: 11pt; }}
QLabel#JobStatus {{ color: {theme.INK}; font-weight: 600; letter-spacing: 0.4px; }}
QLabel#JobEta, QLabel#JobSize, QLabel#JobWhen {{ color: {theme.TEXT}; }}
QLabel#JobError {{ color: {theme.ERROR}; font-size: 9pt; }}
QProgressBar#JobProgress {{ background: #E4EEEB; border: none; border-radius: 4px; }}
QProgressBar#JobProgress::chunk {{
    border-radius: 4px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {theme.LEAF}, stop:1 {theme.OCEAN});
}}
QProgressBar#JobProgress[state="paused"]::chunk {{ background: #9DB8B2; }}
QProgressBar#JobProgress[state="failed"]::chunk {{ background: #E3A79F; }}
QPushButton#OpenButton {{
    color: {theme.WHITE}; font-size: 11pt; border: none; border-radius: 6px; padding: 0;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4CB98E, stop:1 {theme.LEAF});
}}
QPushButton#OpenButton:hover {{ background: {theme.LEAF_DARK}; }}
QFrame#DownloadFooter {{ background: {theme.WHITE}; border-top: 1px solid {theme.BORDER}; }}
QLabel#FooterText {{ color: {theme.MUTED}; font-size: 9pt; }}
"""


class DownloadView(QWidget):
    """Shows all downloads and lets the user pause, resume, retry, cancel and open them."""

    download_started = pyqtSignal(object)  # DownloadJobDTO

    def __init__(self, facade: IBusinessFacade, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DownloadPage")
        self.setStyleSheet(STYLESHEET)
        self._facade = facade
        self._rows: dict[str, tuple[CollapsibleSection, QWidget]] = {}
        self._peak = 0.0

        title = QLabel("Downloads", objectName="PageTitle")
        subtitle = QLabel(
            "Datasets from Google Earth Engine, fetched in chunks and merged into one GeoTIFF as they arrive.",
            objectName="PageSubtitle",
        )
        self.banner = StatusBanner()
        self.banner.setContentsMargins(10, 6, 10, 6)  # wrapped labels ignore stylesheet padding

        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(24, 20, 24, 20)
        column.setSpacing(14)
        column.addWidget(title)
        column.addWidget(subtitle)
        column.addWidget(self.banner)
        column.addWidget(self._build_stats())
        self.queued = CollapsibleSection("QUEUED", "Nothing is downloading. Start a download from Query Input.")
        self.paused = CollapsibleSection("PAUSED", "No paused downloads.")
        self.completed = CollapsibleSection("COMPLETED HISTORY", "Finished downloads appear here.")
        for section in (self.queued, self.paused, self.completed):
            column.addWidget(section)
        column.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(scroll, 1)
        layout.addWidget(self._build_footer())

        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    # ------------------------------------------------------------- building
    def _build_stats(self) -> QFrame:
        card = QFrame(objectName="StatsCard")
        self.chart = SpeedChart()
        self.stats: dict[str, QLabel] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(10)
        names = ("CURRENT", "PEAK", "DOWNLOADED", "REMAINING", "DISK USAGE", "MERGING SPEED")
        for index, name in enumerate(names):
            cell = QVBoxLayout()
            cell.setSpacing(0)
            cell.addWidget(QLabel(f"{name}:", objectName="StatName"))
            value = QLabel("–", objectName="StatValue")
            cell.addWidget(value)
            self.stats[name] = value
            grid.addLayout(cell, index // 3, index % 3)

        self.chunk_setting = QLabel(objectName="ChunkSetting")
        self.change_chunk = QPushButton("Change…", objectName="SecondaryButton")
        self.change_chunk.setCursor(Qt.CursorShape.PointingHandCursor)
        self.change_chunk.setToolTip("Chunk size for downloads started from now on")
        setting = QHBoxLayout()
        setting.addStretch(1)
        setting.addWidget(self.chunk_setting)
        setting.addWidget(self.change_chunk)

        figures = QVBoxLayout()
        figures.addLayout(grid)
        figures.addStretch(1)
        figures.addLayout(setting)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 14, 18, 14)
        layout.setSpacing(20)
        layout.addWidget(self.chart, 3)
        layout.addLayout(figures, 2)
        self.change_chunk.clicked.connect(self._change_chunk_size)
        return card

    def _build_footer(self) -> QFrame:
        footer = QFrame(objectName="DownloadFooter")
        self.location = QLabel(objectName="FooterText")
        self.connection = QLabel("GEE Connection: checking…", objectName="FooterText")
        row = QHBoxLayout(footer)
        row.setContentsMargins(24, 6, 24, 6)
        row.addWidget(self.location, 1)
        row.addWidget(self.connection)
        return footer

    # ------------------------------------------------------------- lifecycle
    def showEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().showEvent(event)
        self.refresh()
        self.check_connection()  # again on every visit, so fixing the setup shows up

    # ------------------------------------------------------------- actions
    def start(self, form: FormDTO) -> None:
        """Start downloading a kept request (called from Query Input)."""
        self.banner.show_info("Preparing the download…")
        run_task(self, self._facade.start_download, form, on_success=self._on_started, on_error=self._show_error)

    def check_connection(self) -> None:
        run_task(self, self._facade.is_gee_available, on_success=self._on_connection, on_error=lambda _: self._on_connection(False))

    def refresh(self) -> None:
        jobs = [job for job in self._facade.list_downloads() if job.status != "cancelled"]
        running = next((job for job in jobs if job.status == JOB_RUNNING), None)
        self._update_stats(jobs, running)

        queued = ([running] if running else []) + [job for job in jobs if job.status == JOB_QUEUED]
        paused = [job for job in jobs if job.status in (JOB_PAUSED, JOB_FAILED)]
        completed = sorted((job for job in jobs if job.status == JOB_COMPLETED), key=lambda j: j.finished_at, reverse=True)
        self._sync(self.queued, queued, JobRow)
        self._sync(self.paused, paused, JobRow)
        self._sync(self.completed, completed, CompletedRow)
        visible = {job.id for job in queued + paused + completed}
        for job_id in [i for i in self._rows if i not in visible]:
            self._remove_row(job_id)

        latest = jobs[-1] if jobs else None
        area = latest.request.aoi_name if latest and latest.request and latest.request.aoi_name else ""
        self.location.setText(f"GEE-Assist  |  Location: {area}" if area else "GEE-Assist")

    def _on_started(self, job: DownloadJobDTO) -> None:
        self.banner.show_success(
            f"Download started: {job.name} ({format_size(job.total_bytes)} in {job.total_chunks} "
            f"chunk{'s' if job.total_chunks != 1 else ''})."
        )
        self.refresh()
        self.download_started.emit(job)

    def _on_connection(self, available: bool) -> None:
        if available:
            self.connection.setText("GEE Connection: Active")
            self.connection.setStyleSheet(f"color: {theme.SUCCESS};")
        else:
            self.connection.setText(
                "GEE Connection: not available (check GEE_PROJECT, `earthengine authenticate` "
                "and that the Earth Engine API is enabled for the project)"
            )
            self.connection.setStyleSheet(f"color: {theme.ERROR};")

    def _start_job(self, job: DownloadJobDTO) -> None:
        action = self._facade.retry_failed_chunks if job.status == JOB_FAILED else self._facade.resume_download
        self._call(action, job)

    def _pause_job(self, job: DownloadJobDTO) -> None:
        self._call(self._facade.pause_download, job)

    def _cancel_job(self, job: DownloadJobDTO) -> None:
        answer = QMessageBox.question(
            self, "Cancel download",
            f"Cancel downloading {job.name}?\nThe files downloaded so far will be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            run_task(self, self._facade.cancel_download, job, on_success=lambda _: self.refresh(), on_error=self._show_error)

    def _open_job(self, job: DownloadJobDTO) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(job.folder))

    def _change_chunk_size(self) -> None:
        current = self._facade.get_chunk_size_mb()
        size, accepted = QInputDialog.getInt(
            self, "Chunk size", "Chunk size for new downloads (MB):", current, MIN_CHUNK_SIZE_MB, MAX_CHUNK_SIZE_MB, 50,
        )
        if accepted and size != current:
            try:
                saved = self._facade.set_chunk_size_mb(size)
            except GeeAssistError as exc:
                self._show_error(exc)
                return
            self.banner.show_info(f"New downloads will use {saved} MB chunks.")
            self._update_chunk_setting()

    def _call(self, action, job: DownloadJobDTO) -> None:
        try:
            action(job)
        except GeeAssistError as exc:
            self._show_error(exc)
        self.refresh()

    def _show_error(self, exc: Exception) -> None:
        self.banner.show_error(str(exc) if isinstance(exc, GeeAssistError) else "Something went wrong. Please try again.")

    # ------------------------------------------------------------- updating
    def _update_stats(self, jobs: list[DownloadJobDTO], running: DownloadJobDTO | None) -> None:
        speed = running.speed_bps if running else 0.0
        self.chart.add_sample(speed, running.average_speed_bps if running else 0.0)
        self._peak = max(self._peak, speed)
        merge_speed = running.merge_speed_bps if running else 0.0  # 0 while nothing is being merged
        values = {
            "CURRENT": format_speed(speed),
            "PEAK": format_speed(self._peak),
            "DOWNLOADED": format_size(running.received_bytes) if running else NONE,  # current download only
            "REMAINING": format_size(max(0, running.total_bytes - running.downloaded_bytes)) if running else NONE,
            "DISK USAGE": format_size(running.disk_bytes) if running else NONE,
            "MERGING SPEED": format_speed(merge_speed),
        }
        for name, value in values.items():
            self.stats[name].setText(value)
        self._update_chunk_setting()

    def _update_chunk_setting(self) -> None:
        self.chunk_setting.setText(f"Chunk size: {self._facade.get_chunk_size_mb()} MB")

    def _sync(self, section: CollapsibleSection, jobs: list[DownloadJobDTO], row_type) -> None:
        """Make ``section`` show one row per job, in order, reusing existing rows."""
        for position, job in enumerate(jobs):
            existing = self._rows.get(job.id)
            if existing and existing[0] is section and isinstance(existing[1], row_type):
                row = existing[1]
                row.update_job(job)
            else:
                if existing:
                    self._remove_row(job.id)
                row = self._make_row(job, row_type)
                self._rows[job.id] = (section, row)
            section.rows.removeWidget(row)
            section.rows.insertWidget(position + 1, row)  # after the "empty" label
        section.set_count(len(jobs))

    def _make_row(self, job: DownloadJobDTO, row_type) -> QWidget:
        row = row_type(job)
        if isinstance(row, JobRow):
            row.start_clicked.connect(self._start_job)
            row.pause_clicked.connect(self._pause_job)
            row.cancel_clicked.connect(self._cancel_job)
        else:
            row.open_clicked.connect(self._open_job)
        return row

    def _remove_row(self, job_id: str) -> None:
        section, row = self._rows.pop(job_id)
        section.rows.removeWidget(row)
        row.deleteLater()

