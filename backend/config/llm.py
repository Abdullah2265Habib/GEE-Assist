"""Gemini settings for interpreting natural-language queries (SRS constraint C-03).

Read from environment variables or a ``.env`` file in the project root:

    GEMINI_API_KEY=your-key          # https://aistudio.google.com/apikey
    GEMINI_MODEL=gemini-3.5-flash-lite    # optional
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from backend.config.download import PROJECT_ROOT

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional; plain environment variables still work
    load_dotenv = None

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
# Tried in order after the configured model. Lighter "lite" models come first: they are
# faster, see less demand, and are accurate enough for filling the form (the entity
# classifier gives them hints). Full Flash models are the fallback.
FALLBACK_MODELS: tuple[str, ...] = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
)


@dataclass(frozen=True)
class LLMSettings:
    api_key: str
    model: str


def load_llm_settings() -> LLMSettings:
    if load_dotenv is not None:
        load_dotenv(PROJECT_ROOT / ".env")
    return LLMSettings(
        api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL,
    )
