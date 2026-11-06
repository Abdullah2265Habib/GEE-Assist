"""Rows and collapsible sections of the Downloads page."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from backend.config import get_dataset
from backend.dto import DownloadJobDTO
from backend.dto.download_dto import (
    CHUNK_DOWNLOADED,
    CHUNK_MERGED,
    JOB_FAILED,
    JOB_PAUSED,
    JOB_QUEUED,
    JOB_RUNNING,
)
from frontend.download_format import format_eta, format_size, format_when

SATELLITE = "\U0001F6F0️"   # 🛰️


def job_title(job: DownloadJobDTO) -> str:
    """e.g. "Sentinel-2 - Faisalabad AOI"."""
    request = job.request
    info = get_dataset(request.dataset) if request else None
    satellite = info.satellite if info and info.satellite else (request.dataset if request else job.name)
    area = request.aoi_name if request and request.aoi_name else "AOI"
    return f"{satellite} - {area}"


def job_details(job: DownloadJobDTO) -> str:
    """Folder name, dates and bands, e.g. "Sentinel-2_73.8231_33.2334 · 2023-01-01 → 2023-12-31 · 2 bands"."""
    parts = [job.name]
    request = job.request
    if request and request.start_date and request.end_date:
        parts.append(f"{request.start_date.isoformat()} → {request.end_date.isoformat()}")
    if job.chunks:
        count = len(job.chunks[0].bands)
        parts.append(f"{count} band{'s' if count != 1 else ''}")
    return "  ·  ".join(parts)


def job_status(job: DownloadJobDTO) -> str:
    percent = f"{job.progress * 100:.0f}%"
    if job.status == JOB_RUNNING:
        merging = next((c for c in job.chunks if c.status == CHUNK_DOWNLOADED), None)
        return f"MERGING CHUNK {merging.id}" if merging else f"DOWNLOADING {percent}"
    if job.status == JOB_QUEUED:
        return "WAITING"
    if job.status == JOB_PAUSED:
        return f"PAUSED {percent}"
    if job.status == JOB_FAILED:
        return f"FAILED {percent}"
    return job.status.upper()


def chunk_summary(job: DownloadJobDTO) -> str:
    """e.g. "Chunk 3 of 4 · 2 merged (1.0 GB)"."""
    merged = sum(c.status == CHUNK_MERGED for c in job.chunks)
    current = min(merged + 1, job.total_chunks)
    text = f"Chunk {current} of {job.total_chunks}"
    if merged:
        text += f"  ·  {merged} merged ({format_size(job.merged_bytes)})"
    return text


class CollapsibleSection(QFrame):
    """A titled card, e.g. "QUEUED (1)", whose body folds away with the chevron."""

    def __init__(self, title: str, empty_text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DownloadSection")
        self._title = title

        self.title_label = QLabel(objectName="SectionHeaderText")
        self.toggle = QToolButton(objectName="SectionToggle")
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.setArrowType(Qt.ArrowType.UpArrow)
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.setToolTip("Show or hide")

        header = QFrame(objectName="SectionHeader")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(16, 8, 10, 8)
        header_row.addWidget(self.title_label, 1)
        header_row.addWidget(self.toggle)

        self.empty_label = QLabel(empty_text, objectName="Muted")
        self.empty_label.setContentsMargins(18, 12, 18, 12)
        self.body = QWidget(objectName="SectionBody")
        self.rows = QVBoxLayout(self.body)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        self.rows.addWidget(self.empty_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self.body)

        self.toggle.toggled.connect(self._set_open)
        self.set_count(0)

    def set_count(self, count: int) -> None:
        self.title_label.setText(f"{self._title} ({count})")
        self.empty_label.setVisible(count == 0)

    def add_row(self, row: QWidget) -> None:
        self.rows.addWidget(row)

    def is_open(self) -> bool:
        return self.toggle.isChecked()

    def _set_open(self, open_: bool) -> None:
        self.body.setVisible(open_)
        self.toggle.setArrowType(Qt.ArrowType.UpArrow if open_ else Qt.ArrowType.DownArrow)


class JobRow(QFrame):
    """A download that is running, waiting, paused or failed."""

    start_clicked = pyqtSignal(object)    # DownloadJobDTO
    pause_clicked = pyqtSignal(object)
    cancel_clicked = pyqtSignal(object)

    def __init__(self, job: DownloadJobDTO, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("JobRow")
        self.job = job

        icon = QLabel(SATELLITE, objectName="SatelliteIcon")
        icon.setFixedWidth(36)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel(objectName="JobTitle")
        self.details = QLabel(objectName="Muted")
        self.chunks = QLabel(objectName="Muted")
        names = QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(self.title)
        names.addWidget(self.details)
        names.addWidget(self.chunks)

        self.status = QLabel(objectName="JobStatus")
        self.eta = QLabel(objectName="JobEta")
        self.size = QLabel(objectName="JobSize")
        figures = QHBoxLayout()
        figures.addWidget(self.status)
        figures.addStretch(1)
        figures.addWidget(self.eta)
        figures.addSpacing(36)
        figures.addWidget(self.size)

        self.bar = QProgressBar(objectName="JobProgress")
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)

        self.error = QLabel(objectName="JobError")
        self.error.setWordWrap(True)
        self.start_button = QPushButton("Start", objectName="SecondaryButton")
        self.pause_button = QPushButton("Pause", objectName="SecondaryButton")
        self.cancel_button = QPushButton("Cancel", objectName="SecondaryButton")
        buttons = QHBoxLayout()
        buttons.addWidget(self.error, 4)
        buttons.addStretch(1)  # keeps the buttons compact and on the right
        for button in (self.start_button, self.pause_button, self.cancel_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedWidth(88)
            buttons.addWidget(button)

        progress = QVBoxLayout()
        progress.setSpacing(6)
        progress.addLayout(figures)
        progress.addWidget(self.bar)
        progress.addLayout(buttons)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(names, 4)
        layout.addLayout(progress, 6)

        self.start_button.clicked.connect(lambda: self.start_clicked.emit(self.job))
        self.pause_button.clicked.connect(lambda: self.pause_clicked.emit(self.job))
        self.cancel_button.clicked.connect(lambda: self.cancel_clicked.emit(self.job))
        self.update_job(job)

    def update_job(self, job: DownloadJobDTO) -> None:
        self.job = job
        self.title.setText(job_title(job))
        self.details.setText(job_details(job))
        self.chunks.setText(chunk_summary(job))
        self.status.setText(job_status(job))
        self.eta.setText(f"ETA: {format_eta(job.eta_seconds)}" if job.status == JOB_RUNNING else "")
        self.size.setText(f"{format_size(job.downloaded_bytes)} / {format_size(job.total_bytes)}")
        self.bar.setValue(round(job.progress * 1000))
        self.bar.setProperty("state", job.status)
        self.bar.style().unpolish(self.bar)
        self.bar.style().polish(self.bar)

        self.error.setText(job.error)
        self.error.setVisible(bool(job.error))
        self.start_button.setText("Retry" if job.status == JOB_FAILED else "Start")
        self.start_button.setEnabled(job.status in (JOB_PAUSED, JOB_FAILED))
        self.start_button.setToolTip("Retry the failed chunks" if job.status == JOB_FAILED else "Continue where it stopped")
        self.pause_button.setEnabled(job.status in (JOB_RUNNING, JOB_QUEUED))
        self.pause_button.setToolTip("Stop after the current request; finished parts are kept")
        self.cancel_button.setToolTip("Stop and delete the downloaded files")


class CompletedRow(QFrame):
    """A finished download; the green button opens its folder."""

    open_clicked = pyqtSignal(object)  # DownloadJobDTO

    def __init__(self, job: DownloadJobDTO, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("JobRow")
        self.job = job

        self.title = QLabel(objectName="JobTitle")
        self.details = QLabel(objectName="Muted")
        names = QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(self.title)
        names.addWidget(self.details)

        self.when = QLabel(objectName="JobWhen")
        self.open_button = QPushButton("▶", objectName="OpenButton")
        self.open_button.setFixedSize(30, 28)
        self.open_button.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.addLayout(names, 1)
        layout.addWidget(self.when)
        layout.addSpacing(10)
        layout.addWidget(self.open_button)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.open_button.clicked.connect(lambda: self.open_clicked.emit(self.job))
        self.update_job(job)

    def update_job(self, job: DownloadJobDTO) -> None:
        self.job = job
        self.title.setText(job_title(job))
        size = format_size(job.dataset.size_bytes) if job.dataset else ""
        self.details.setText("  ·  ".join(p for p in (job.name, size) if p))
        self.when.setText(f"Completed: {format_when(job.finished_at)}")
        path = job.dataset.path if job.dataset else job.folder
        self.open_button.setToolTip(f"Open the folder\n{path}")
