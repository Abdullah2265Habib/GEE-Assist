"""User-changeable download settings, kept in a JSON file.

    workspace/download_settings.json
    {
      "chunk_size_mb": 500,
      "retry_limit": 3
    }

The file is created with the defaults the first time it is read. Editing it (or
changing the chunk size on the Downloads page) affects downloads started afterwards;
a running download keeps the chunks it was split into.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from backend.config.download import PROJECT_ROOT
from backend.exceptions import ValidationError

logger = logging.getLogger(__name__)

SETTINGS_FILE = PROJECT_ROOT / "workspace" / "download_settings.json"

DEFAULT_CHUNK_SIZE_MB = 500
MIN_CHUNK_SIZE_MB = 1
MAX_CHUNK_SIZE_MB = 100 * 1024     # 100 GB
DEFAULT_RETRY_LIMIT = 3            # attempts per chunk before the job is marked failed
MAX_RETRY_LIMIT = 20

BYTES_PER_MB = 1024 * 1024


@dataclass(frozen=True)
class DownloadSettings:
    chunk_size_mb: int = DEFAULT_CHUNK_SIZE_MB
    retry_limit: int = DEFAULT_RETRY_LIMIT

    @property
    def chunk_size_bytes(self) -> int:
        return self.chunk_size_mb * BYTES_PER_MB

    def validate(self) -> None:
        if not isinstance(self.chunk_size_mb, int) or not MIN_CHUNK_SIZE_MB <= self.chunk_size_mb <= MAX_CHUNK_SIZE_MB:
            raise ValidationError(f"Chunk size must be a whole number of MB from {MIN_CHUNK_SIZE_MB} to {MAX_CHUNK_SIZE_MB}.")
        if not isinstance(self.retry_limit, int) or not 0 <= self.retry_limit <= MAX_RETRY_LIMIT:
            raise ValidationError(f"Retry limit must be a whole number from 0 to {MAX_RETRY_LIMIT}.")


class DownloadSettingsStore:
    """Reads and writes ``DownloadSettings`` as JSON."""

    def __init__(self, path: Path | str = SETTINGS_FILE):
        self.path = Path(path)

    def load(self) -> DownloadSettings:
        if not self.path.exists():
            settings = DownloadSettings()
            self.save(settings)
            return settings
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            known = {k: v for k, v in data.items() if k in DownloadSettings.__dataclass_fields__}
            settings = DownloadSettings(**known)
            settings.validate()
            return settings
        except (OSError, ValueError, TypeError, AttributeError, ValidationError):
            logger.warning("%s is not valid; using the default download settings", self.path, exc_info=True)
            return DownloadSettings()

    def save(self, settings: DownloadSettings) -> None:
        settings.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(settings), indent=2) + "\n", encoding="utf-8")

    def set_chunk_size_mb(self, chunk_size_mb: int) -> DownloadSettings:
        current = self.load()
        settings = DownloadSettings(chunk_size_mb=chunk_size_mb, retry_limit=current.retry_limit)
        self.save(settings)
        return settings
