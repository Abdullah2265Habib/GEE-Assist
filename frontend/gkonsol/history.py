"""The commands typed in gkonsol, kept between sessions.

They are saved with the terminal's height in ``workspace/gkonsol.json``:

    {
      "history": ["gee verify", "download watch"],
      "panel_height": 280
    }

As in other shells, ``!!`` runs the last command again, ``!12`` the 12th in the
``history`` list, ``!-2`` the one before the last, and ``!gee`` the last one starting
with "gee". Words after the reference are added to it: ``!! --detach``.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from backend.config.download import PROJECT_ROOT
from frontend.gkonsol.parser import UsageError

logger = logging.getLogger(__name__)

STORE_FILE = PROJECT_ROOT / "workspace" / "gkonsol.json"
HISTORY_LIMIT = 500

_REFERENCE = re.compile(r"^!(!|-?\d+|[^\s!]+)(.*)$", re.DOTALL)


class GkonsolStore:
    """gkonsol's saved settings: a small JSON file. Unreadable files count as empty."""

    def __init__(self, path: Path | str = STORE_FILE):
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def update(self, **values: Any) -> None:
        data = self.load()
        data.update(values)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        except OSError:
            logger.warning("Could not save %s", self.path, exc_info=True)


class History:
    def __init__(self, store: Optional[GkonsolStore] = None, limit: int = HISTORY_LIMIT):
        self._store = store
        self._limit = limit
        saved = store.load().get("history", []) if store else []
        self.entries: list[str] = [entry for entry in saved if isinstance(entry, str)][-limit:]

    def add(self, command_line: str) -> None:
        command_line = command_line.strip()
        if not command_line or (self.entries and self.entries[-1] == command_line):
            return
        self.entries.append(command_line)
        del self.entries[:-self._limit]
        self._save()

    def clear(self) -> None:
        self.entries = []
        self._save()

    def expand(self, command_line: str) -> str:
        """``command_line`` with a ``!`` reference at its start replaced by the command it names."""
        match = _REFERENCE.match(command_line.strip())
        if not match:
            return command_line
        reference, rest = match.groups()
        found: Optional[str] = None
        if reference == "!":
            found = self.entries[-1] if self.entries else None
        elif reference.lstrip("-").isdigit():
            number = int(reference)
            if 0 < number <= len(self.entries):
                found = self.entries[number - 1]
            elif -len(self.entries) <= number < 0:
                found = self.entries[number]
        else:
            found = next((entry for entry in reversed(self.entries) if entry.startswith(reference)), None)
        if found is None:
            raise UsageError(f"!{reference}: no such command in the history.")
        return found + rest

    def _save(self) -> None:
        if self._store is not None:
            self._store.update(history=self.entries)
