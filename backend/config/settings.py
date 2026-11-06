"""Desktop-app settings, read from environment variables (and an optional ``.env`` file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional; plain environment variables still work
    load_dotenv = None

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


@lru_cache
def get_settings() -> Settings:
    if load_dotenv is not None:
        load_dotenv(PROJECT_ROOT / ".env")
    return Settings(
        auth_api_url=os.getenv("AUTH_API_URL", Settings.auth_api_url).rstrip("/"),
        auth_api_timeout=float(os.getenv("AUTH_API_TIMEOUT", Settings.auth_api_timeout)),
        keyring_service=os.getenv("KEYRING_SERVICE", Settings.keyring_service),
    )
