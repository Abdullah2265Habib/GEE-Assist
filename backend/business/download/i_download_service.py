from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

from backend.dto import CheckDTO, DownloadJobDTO, FormDTO


class IDownloadService(ABC):
    """Class diagram: IDownloadService (startDownload, getProgress, retryFailedChunks).

    pause / resume / cancel / list_jobs and the chunk-size and access checks extend
    the diagram for the Downloads page.
    Every method returns a snapshot of the job; poll ``get_progress`` for updates.
    """

    @abstractmethod
    def start_download(self, form: FormDTO) -> DownloadJobDTO:
        """Split the request into chunks and queue it. Downloads run one at a time."""

    @abstractmethod
    def get_progress(self, job: DownloadJobDTO) -> DownloadJobDTO:
        """Current state of the job: status, chunks, bytes, speed and ETA."""

    @abstractmethod
    def retry_failed_chunks(self, job: DownloadJobDTO) -> DownloadJobDTO:
        """Queue a failed job again; its failed chunks start a fresh set of retries."""

    @abstractmethod
    def pause(self, job: DownloadJobDTO) -> DownloadJobDTO:
        """Stop after the current GEE request; finished tiles and chunks are kept."""

    @abstractmethod
    def resume(self, job: DownloadJobDTO) -> DownloadJobDTO:
        """Queue a paused job again; it continues where it stopped."""

    @abstractmethod
    def cancel(self, job: DownloadJobDTO) -> DownloadJobDTO:
        """Stop the job and delete its folder."""

    @abstractmethod
    def list_jobs(self) -> list[DownloadJobDTO]:
        """Every known job, oldest first, including those saved by earlier sessions."""

    @abstractmethod
    def chunk_size_mb(self) -> int:
        """Chunk size used for new downloads (from download_settings.json)."""

    @abstractmethod
    def set_chunk_size_mb(self, size_mb: int) -> int:
        """Change the chunk size for downloads started afterwards; returns the saved size."""

    @abstractmethod
    def is_gee_available(self) -> bool:
        """True if Google Earth Engine is signed in and usable."""

    @abstractmethod
    def check_gee_setup(self) -> list[CheckDTO]:
        """The Earth Engine set-up checked step by step (gkonsol's ``gee verify``)."""

    @abstractmethod
    def begin_gee_sign_in(self) -> str:
        """Start signing this computer in to Earth Engine; returns the Google page to open."""

    @abstractmethod
    def complete_gee_sign_in(self, should_stop: Optional[Callable[[], bool]] = None) -> str:
        """Wait for the browser to come back and save the sign-in; returns the credentials file."""

    @abstractmethod
    def cancel_gee_sign_in(self) -> None:
        """Stop waiting for the Earth Engine browser sign-in."""

    @abstractmethod
    def shutdown(self, timeout: float = 5.0) -> None:
        """Pause the active download so it resumes next time, and stop the worker."""
