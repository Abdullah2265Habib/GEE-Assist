"""Names of downloaded datasets: ``<satellite>_<longitude>_<latitude>_<started>``.

The coordinates are the centre of the AOI's bounding box with 4 decimals (about
11 m); ``<started>`` is when the download was started, as ``YYYY-MM-DD_HH-MM-SS``
(no ``:``, which Windows does not allow in file names),
e.g. ``Sentinel-2_73.8231_33.2334_2026-11-06_21-30-15``.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from backend.business.request.geojson_utils import geometry_bbox
from backend.config import get_dataset
from backend.dto import FormDTO


STARTED_FORMAT = "%Y-%m-%d_%H-%M-%S"


def dataset_folder_name(form: FormDTO, started: datetime) -> str:
    info = get_dataset(form.dataset)
    satellite = (info.satellite if info and info.satellite else form.dataset) or "dataset"
    satellite = re.sub(r"[^A-Za-z0-9.-]+", "-", satellite).strip("-")
    west, south, east, north = geometry_bbox(json.loads(form.aoi))
    return f"{satellite}_{(west + east) / 2:.4f}_{(south + north) / 2:.4f}_{started.strftime(STARTED_FORMAT)}"


def unique_folder(parent: Path, name: str) -> Path:
    """``parent / name``, or ``name_2``, ``name_3``, ... if that folder already exists."""
    folder = parent / name
    number = 2
    while folder.exists():
        folder = parent / f"{name}_{number}"
        number += 1
    return folder
