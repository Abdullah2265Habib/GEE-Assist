"""Desktop-app settings, read from environment variables (and an optional ``.env`` file)."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional; plain environment variables still work
    load_dotenv = None

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets"


@dataclass(frozen=True)
class Settings:
    # Base URL of the GEE-Assist authentication server (GEE-Assist-Backend).
    auth_api_url: str = "http://localhost:8000"
    # Seconds to wait for the authentication server before giving up.
    auth_api_timeout: float = 15.0
    # Name under which the refresh token is kept in the OS credential store.
    keyring_service: str = "GEE-Assist"
    # How long "Keep me signed in" lasts, in seconds, counted from signing in.
    session_duration: float = 7 * 24 * 3600
    # Google Cloud project registered for Earth Engine (dataset downloads).
    gee_project: str = ""


_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(text: str) -> float:
    """Turn "90s", "2m", "12h" or "7d" into seconds. A bare number means days."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smhd]?)\s*", text.lower())
    if not match or float(match.group(1)) <= 0:
        raise ValueError(f"Invalid duration {text!r}: use a positive number with s, m, h or d, e.g. 7d.")
    return float(match.group(1)) * _UNIT_SECONDS[match.group(2) or "d"]


def _session_duration() -> float:
    text = os.getenv("SESSION_DURATION")
    if not text:
        return Settings.session_duration
    try:
        return parse_duration(text)
    except ValueError:
        logger.warning("SESSION_DURATION=%r is not valid; using 7 days", text)
        return Settings.session_duration


@lru_cache
def get_settings() -> Settings:
    if load_dotenv is not None:
        load_dotenv(PROJECT_ROOT / ".env")
    return Settings(
        auth_api_url=os.getenv("AUTH_API_URL", Settings.auth_api_url).rstrip("/"),
        auth_api_timeout=float(os.getenv("AUTH_API_TIMEOUT", Settings.auth_api_timeout)),
        keyring_service=os.getenv("KEYRING_SERVICE", Settings.keyring_service),
        session_duration=_session_duration(),
        gee_project=os.getenv("GEE_PROJECT", Settings.gee_project).strip(),
    )
