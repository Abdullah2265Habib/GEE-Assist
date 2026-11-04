"""Paths to the files in the project's ``assets`` folder."""

from __future__ import annotations

from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"

STARTING_VIDEO = ASSETS_DIR / "starting_video" / "start.mp4"
EARTH_SVG = ASSETS_DIR / "resources" / "Satellite around Earth.svg"
APP_ICON = ASSETS_DIR / "project_icon" / "2. icon.png"
