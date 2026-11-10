"""Helpers shared by gkonsol's commands: confirmations, typed values, times and sizes."""

from __future__ import annotations

import re
import time
from datetime import date, datetime
from typing import Any, Callable, Generator, Optional

from backend.config import DATASET_ALIASES, DATASETS, DatasetInfo
from frontend.gkonsol.effects import Ask
from frontend.gkonsol.parser import Option, UsageError

YES = Option("yes", "Do not ask for confirmation", short="y")

ON_WORDS = ("on", "show", "open", "expand", "true", "yes")
OFF_WORDS = ("off", "hide", "close", "collapse", "false", "no")
SWITCH_WORDS = ("on", "off", "toggle")


def confirm(question: str, assume_yes: bool = False, default: bool = False) -> Generator[Any, Any, bool]:
    """Ask a yes/no question (``yield from confirm(...)``). ``assume_yes`` (``-y``) skips it."""
    if assume_yes:
        return True
    answer = yield Ask(f"{question} {'[Y/n]' if default else '[y/N]'}", default="y" if default else "n",
                       choices=("y", "n"))
    return answer.strip().lower() in ("y", "yes")


def switch(word: Optional[str], current: bool) -> bool:
    """The new state for "on", "off" or "toggle" (nothing typed toggles too)."""
    if word is None or word == "toggle":
        return not current
    if word.lower() in ON_WORDS:
        return True
    if word.lower() in OFF_WORDS:
        return False
    raise UsageError(f"Expected on, off or toggle, not '{word}'.")


def timed(fn: Callable[..., Any], *args: Any) -> tuple[Any, float]:
    """``fn(*args)`` and how long it took in milliseconds (run as a background task)."""
    started = time.perf_counter()
    result = fn(*args)
    return result, (time.perf_counter() - started) * 1000


# ----------------------------------------------------------------------------- typed values
def to_int(word: str, what: str, lowest: Optional[int] = None, highest: Optional[int] = None) -> int:
    try:
        value = int(word.replace("_", "").replace(",", ""))
    except ValueError:
        raise UsageError(f"{what} must be a whole number, not '{word}'.") from None
    if (lowest is not None and value < lowest) or (highest is not None and value > highest):
        raise UsageError(f"{what} must be from {lowest} to {highest}.")
    return value


def to_float(word: str, what: str, lowest: Optional[float] = None, highest: Optional[float] = None) -> float:
    try:
        value = float(word)
    except ValueError:
        raise UsageError(f"{what} must be a number, not '{word}'.") from None
    if (lowest is not None and value < lowest) or (highest is not None and value > highest):
        raise UsageError(f"{what} must be from {lowest:g} to {highest:g}.")
    return value


def to_date(word: str, what: str = "The date") -> date:
    try:
        return date.fromisoformat(word)
    except ValueError:
        raise UsageError(f"{what} must be written YYYY-MM-DD, e.g. 2024-06-01 (not '{word}').") from None


_DISTANCE = re.compile(r"^(\d+(?:\.\d+)?)\s*(m|km)?$", re.IGNORECASE)


def to_metres(word: str, what: str = "The radius") -> float:
    """"500", "500m" or "2.5km" in metres."""
    match = _DISTANCE.match(word.strip())
    if not match or float(match.group(1)) <= 0:
        raise UsageError(f"{what} must be a distance such as 500m or 2.5km, not '{word}'.")
    value = float(match.group(1))
    return value * 1000 if (match.group(2) or "m").lower() == "km" else value


def find_dataset(word: str) -> DatasetInfo:
    """A dataset by its key, a common name ("landsat-8", "s2") or the start of its key."""
    key = word.strip().lower()
    if key in DATASETS:
        return DATASETS[key]
    spaced = key.replace("_", " ").replace("-", " ")
    for dataset_key, aliases in DATASET_ALIASES.items():
        if any(spaced == alias.replace("-", " ") for alias in aliases):
            return DATASETS[dataset_key]
    starting = [info for dataset_key, info in DATASETS.items() if dataset_key.startswith(key)]
    if len(starting) == 1:
        return starting[0]
    if starting:
        raise UsageError(f"'{word}' could be {', '.join(info.key for info in starting)}: type more of it.")
    raise UsageError(f"Unknown dataset '{word}'. 'datasets list' shows them.")


# ----------------------------------------------------------------------------- display
def when(moment: Optional[datetime]) -> str:
    """A date and time in the computer's time zone: "10 Nov 2026, 18:33"."""
    if moment is None:
        return "—"
    if moment.tzinfo is not None:
        moment = moment.astimezone()
    return moment.strftime("%d %b %Y, %H:%M")


def duration(seconds: Optional[float]) -> str:
    """"6 d 23 h", "2 h 05 min", "12 min", "45 s"."""
    if seconds is None:
        return "—"
    total = int(max(0, seconds))
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    if days:
        return f"{days} d {hours} h"
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min"
    return f"{secs} s"
