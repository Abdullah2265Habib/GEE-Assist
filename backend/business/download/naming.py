"""Names of downloaded datasets: ``<satellite>_<longitude>_<latitude>_<start date>_<end date>``.

The coordinates are the centre of the AOI's bounding box with 4 decimals (about
11 m); the dates are the request's date range as ``YYYY-MM-DD``,
e.g. ``Sentinel-2_73.8231_33.2334_2023-01-01_2023-12-31``. A date the request
does not have is left out.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.business.request.geojson_utils import geometry_bbox
from backend.config import get_dataset
from backend.dto import FormDTO


def dataset_folder_name(form: FormDTO) -> str:
    info = get_dataset(form.dataset)
    satellite = (info.satellite if info and info.satellite else form.dataset) or "dataset"
    satellite = re.sub(r"[^A-Za-z0-9.-]+", "-", satellite).strip("-")
    west, south, east, north = geometry_bbox(json.loads(form.aoi))
    parts = [satellite, f"{(west + east) / 2:.4f}", f"{(south + north) / 2:.4f}"]
    parts += [day.isoformat() for day in (form.start_date, form.end_date) if day]
    return "_".join(parts)


_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TIME = re.compile(r"\d{2}-\d{2}-\d{2}")  # older names ended with the download time


def parse_dataset_name(name: str) -> tuple[str, str, str]:
    """The satellite, start date and end date in a download name ("" for what it does not have).

    The reverse of ``dataset_folder_name``; older names ended with the download time
    (``..._2026-11-07_00-11-04``) instead of the date range, and a repeated download
    has ``_2``, ``_3``, ... at the end.
    """
    parts = name.split("_")
    if len(parts) < 3:
        return "", "", ""
    dates = [part for part in parts[3:5] if _DATE.fullmatch(part)]
    if len(parts) > 4 and _TIME.fullmatch(parts[4]):
        dates = []  # the download date and time, not a date range
    start, end = (dates + ["", ""])[:2]
    return parts[0], start, end


def unique_folder(parent: Path, name: str) -> Path:
    """``parent / name``, or ``name_2``, ``name_3``, ... if that folder already exists."""
    folder = parent / name
    number = 2
    while folder.exists():
        folder = parent / f"{name}_{number}"
        number += 1
    return folder
