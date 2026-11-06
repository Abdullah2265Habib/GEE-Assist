"""How sizes, speeds and times are shown on the Downloads page.

Sizes use decimal units like the chunk size setting (2 GB = 4 chunks of 500 MB).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

_UNITS = ("B", "KB", "MB", "GB", "TB")


def format_size(byte_count: float) -> str:
    value = float(max(byte_count, 0))
    for unit in _UNITS:
        if value < 1000 or unit == _UNITS[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return f"{value:.1f} TB"


def format_speed(bytes_per_second: float) -> str:
    return f"{format_size(bytes_per_second)}/s"


def format_eta(seconds: Optional[float]) -> str:
    """mm:ss, or h:mm:ss for an hour or more; "--:--" when unknown."""
    if seconds is None:
        return "--:--"
    total = int(round(max(seconds, 0)))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def format_when(iso_timestamp: str, today: Optional[date] = None) -> str:
    """"Today 10:15 AM", "Yesterday 3:30 PM", "Mon 9:05 AM" (this week) or "Jun 5, 2026 2:23 AM"."""
    if not iso_timestamp:
        return ""
    moment = datetime.fromisoformat(iso_timestamp)
    today = today or date.today()
    clock = moment.strftime("%I:%M %p").lstrip("0")
    days = (today - moment.date()).days
    if days == 0:
        return f"Today {clock}"
    if days == 1:
        return f"Yesterday {clock}"
    if 1 < days < 7:
        return f"{moment.strftime('%a')} {clock}"
    return f"{moment.strftime('%b')} {moment.day}, {moment.year} {clock}"
