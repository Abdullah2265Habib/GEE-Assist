"""Check Gemini's interpretation of a query against what GEE-Assist supports.

The LLM can pick a dataset that does not exist, bands from another dataset,
dates outside the archive or an analysis the dataset cannot do (SRS C-07).
Everything is corrected or dropped here, with a note telling the user what
was not taken over, so the form only ever receives valid choices.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date

from backend.business.request.geojson_utils import validate_geometry
from backend.config import COMPOSITE_METHODS, get_dataset
from backend.dto import FormDTO


def check_interpretation(form: FormDTO, today: date | None = None) -> FormDTO:
    today = today or date.today()
    notes: list[str] = []
    info = get_dataset(form.dataset)

    if info is None:
        if form.dataset:
            notes.append(f'Gemini suggested an unsupported dataset ("{form.dataset}"); choose one yourself.')
        # Nothing dataset-specific can be trusted without a dataset; keep place and time only.
        return replace(
            form, dataset="", bands=[], scale=None, max_cloud_cover=None, composite="",
            analysis_type="", processes=[], **_checked_place_and_time(form, None, today, notes),
            notes=notes,
        )

    bands = [b for b in form.bands if b in info.bands]
    dropped = [b for b in form.bands if b not in info.bands]
    if dropped:
        notes.append(f"Ignored bands not in {info.name}: {', '.join(dropped)}.")
    if not bands:
        bands = list(info.default_bands)

    scale = form.scale if form.scale and form.scale > 0 else info.default_scale
    cloud = form.max_cloud_cover if info.supports_cloud_filter else None
    composite = form.composite if form.composite in COMPOSITE_METHODS else info.default_composite

    analysis, processes = form.analysis_type, list(form.processes)
    if analysis and analysis not in info.supported_analyses:
        notes.append(f"{info.name} cannot do {analysis} analysis, so no analysis was selected.")
        analysis, processes = "", []
    elif analysis:
        supported = info.supported_analyses[analysis]
        unsupported = [p for p in processes if p not in supported]
        if unsupported:
            notes.append(f"Ignored processes not available for {info.name}: {', '.join(unsupported)}.")
        processes = [p for p in processes if p in supported]
    else:
        processes = []

    return replace(
        form, bands=bands, scale=scale, max_cloud_cover=cloud, composite=composite,
        analysis_type=analysis, processes=processes,
        **_checked_place_and_time(form, info, today, notes), notes=notes,
    )


def _checked_place_and_time(form: FormDTO, info, today: date, notes: list[str]) -> dict:
    aoi = form.aoi
    if aoi:
        try:
            error = validate_geometry(json.loads(aoi))
        except json.JSONDecodeError:
            error = "invalid geometry"
        if error:
            notes.append("The area Gemini suggested was not usable; draw or import it yourself.")
            aoi = ""

    start, end = form.start_date, form.end_date
    if start and end and start > end:
        start, end = end, start
    lowest = info.min_date if info else None
    highest = min(info.max_date, today) if info and info.max_date else today
    if end and end > highest:
        notes.append(f"End date moved to {highest.isoformat()} (no data after that).")
        end = highest
    if lowest and start and start < lowest:
        notes.append(f"Start date moved to {lowest.isoformat()} ({info.name} starts then).")
        start = lowest
    if start and end and start > end:  # the whole range was outside the archive
        notes.append("The requested dates are outside the dataset's archive; pick dates yourself.")
        start = end = None

    return {"aoi": aoi, "start_date": start, "end_date": end}
