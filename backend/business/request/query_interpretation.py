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
from backend.business.request.query_entities import date_range
from backend.config import ANALYSIS_CATEGORIES, COMPOSITE_METHODS, get_dataset
from backend.dto import EntityDTO, FormDTO


def check_interpretation(form: FormDTO, today: date | None = None) -> FormDTO:
    today = today or date.today()
    notes: list[str] = list(form.notes)  # keep notes from earlier steps
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


# ----------------------------------------------------------------------------- named entities
def _unique(entities: list[EntityDTO], label: str) -> list[str]:
    return list(dict.fromkeys(e.value for e in entities if e.label == label and e.value))


def _category_of(process: str) -> str:
    return next(cat for cat, processes in ANALYSIS_CATEGORIES.items() if process in processes)


def ground_with_entities(form: FormDTO, entities: list[EntityDTO]) -> FormDTO:
    """Make what the user explicitly wrote win over the LLM's guess.

    Datasets, processes, bands, cloud cover, resolution and composite named in
    the query override Gemini's choice; dates and place only fill gaps, because
    Gemini resolves phrases like "last summer" better than patterns do.
    """
    notes = list(form.notes)
    changes: dict = {}

    datasets = _unique(entities, "DATASET")
    if len(datasets) == 1 and datasets[0] != form.dataset:
        wanted, suggested = get_dataset(datasets[0]), get_dataset(form.dataset)
        if suggested is not None:
            notes.append(f"Used {wanted.name} as written in your request (Gemini suggested {suggested.name}).")
        changes.update(dataset=datasets[0], bands=[])  # bands chosen for another dataset don't apply

    if bands := _unique(entities, "BAND"):
        changes["bands"] = bands
    if cloud := _unique(entities, "CLOUD_COVER"):
        changes["max_cloud_cover"] = int(cloud[-1])
    if resolution := _unique(entities, "RESOLUTION"):
        changes["scale"] = int(resolution[-1])
    if composite := _unique(entities, "COMPOSITE"):
        changes["composite"] = composite[-1]

    if processes := _unique(entities, "PROCESS"):
        categories = list(dict.fromkeys(_category_of(p) for p in processes))
        category = form.analysis_type if form.analysis_type in categories else categories[0]
        named = [p for p in processes if _category_of(p) == category]
        kept = [p for p in form.processes if p not in named] if form.analysis_type == category else []
        changes.update(analysis_type=category, processes=named + kept)

    if form.start_date is None and form.end_date is None:
        start, end = date_range(entities)
        if start:
            changes.update(start_date=start, end_date=end)

    places = list(dict.fromkeys(e.value for e in entities if e.label == "PLACE"))
    if places and not form.aoi_name:
        changes["aoi_name"] = ", ".join(places)
    if places and not form.aoi:
        notes.append(f"Couldn't locate {', '.join(places)} automatically; draw the area on the map.")

    return replace(form, **changes, notes=notes, entities=list(entities))


def has_form_values(form: FormDTO) -> bool:
    return any((form.dataset, form.processes, form.bands, form.start_date, form.aoi,
                form.max_cloud_cover is not None, form.scale))
