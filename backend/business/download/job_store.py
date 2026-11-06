"""Saves download jobs so they survive closing the app (UC-05 7a: progress is saved for resumption).

Each job is written to ``<job folder>/download.json``; a registry file lists the job
folders, since users can download into any folder.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from backend.config.download import PROJECT_ROOT
from backend.dto import DownloadJobDTO

logger = logging.getLogger(__name__)

MANIFEST_NAME = "download.json"
REGISTRY_FILE = PROJECT_ROOT / "workspace" / "download_jobs.json"


class DownloadJobStore:
    def __init__(self, registry_path: Path | str = REGISTRY_FILE):
        self.registry_path = Path(registry_path)
        self._lock = threading.Lock()

    def save(self, job: DownloadJobDTO) -> None:
        folder = Path(job.folder)
        folder.mkdir(parents=True, exist_ok=True)
        _write_json(folder / MANIFEST_NAME, job.to_dict())
        with self._lock:
            folders = self._read_registry()
            if job.folder not in folders:
                folders.append(job.folder)
                _write_json(self.registry_path, folders)

    def load_all(self) -> list[DownloadJobDTO]:
        """Jobs from every registered folder that still has a readable manifest."""
        jobs: list[DownloadJobDTO] = []
        with self._lock:
            folders = self._read_registry()
            kept = []
            for folder in folders:
                manifest = Path(folder) / MANIFEST_NAME
                try:
                    jobs.append(DownloadJobDTO.from_dict(json.loads(manifest.read_text(encoding="utf-8"))))
                    kept.append(folder)
                except FileNotFoundError:
                    continue  # folder deleted outside the app: forget it
                except (OSError, ValueError, TypeError, KeyError):
                    logger.warning("Skipping unreadable download manifest %s", manifest, exc_info=True)
                    kept.append(folder)
            if kept != folders:
                _write_json(self.registry_path, kept)
        return jobs

    def forget(self, job: DownloadJobDTO) -> None:
        with self._lock:
            folders = [f for f in self._read_registry() if f != job.folder]
            _write_json(self.registry_path, folders)

    def _read_registry(self) -> list[str]:
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
            return [str(f) for f in data] if isinstance(data, list) else []
        except FileNotFoundError:
            return []
        except (OSError, ValueError):
            logger.warning("Download registry %s is not readable; starting a new one", self.registry_path)
            return []


def _write_json(path: Path, data) -> None:
    """Write via a temporary file so a crash never leaves half a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temporary, path)
