"""The theme the user chose, kept in ``workspace/appearance.json``.

No file (or an unknown theme in it) means the user has not chosen yet: the app
then uses the light theme and asks on start-up.
"""

from __future__ import annotations

import json
from pathlib import Path

SETTINGS_FILE = Path(__file__).resolve().parents[1] / "workspace" / "appearance.json"

THEMES = {                      # name -> label shown to the user
    "light": "Light",
    "dark-green": "Dark – blue-green",
    "dark-grey": "Dark – grey",
}
DEFAULT_THEME = "light"


def saved_theme(path: Path = SETTINGS_FILE) -> str | None:
    """The theme the user chose, or None if they have not chosen one."""
    try:
        name = json.loads(Path(path).read_text(encoding="utf-8")).get("theme")
    except (OSError, ValueError, AttributeError):
        return None
    return name if name in THEMES else None


def current_theme(path: Path = SETTINGS_FILE) -> str:
    return saved_theme(path) or DEFAULT_THEME


def save_theme(name: str, path: Path = SETTINGS_FILE) -> None:
    if name not in THEMES:
        raise ValueError(f"Unknown theme: {name!r}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"theme": name}, indent=2), encoding="utf-8")
