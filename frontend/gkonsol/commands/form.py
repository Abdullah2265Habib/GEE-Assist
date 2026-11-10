"""Parameter form commands: form (show, set, aoi, reset, validate, estimate, wizard, submit) and ask.

The commands fill the parameter form on the Query Input page, the same form the user
sees. Values are checked here before they reach the form, so a value the form's
fields cannot hold (a band of another dataset, a date outside the dataset) is refused
with a message instead of being changed silently.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Generator, Optional, Sequence

from backend.config import (
    ANALYSIS_CATEGORIES,
    AUTO_UTM,
    BYTES_PER_PIXEL,
    COMPOSITE_METHODS,
    CRS_OPTIONS,
    GEE_MAX_GRID_DIMENSION,
    GEE_MAX_REQUEST_BYTES,
    GEE_REQUEST_BYTES_PER_PIXEL,
    DatasetInfo,
    get_dataset,
)
from backend.config.download_settings import BYTES_PER_MB
from backend.dto import FormDTO, ValidationDTO
from backend.exceptions import GeeAssistError
from frontend.aoi_geometry import (
    bbox_of,
    bbox_polygon,
    circle_polygon,
    estimate_download,
    format_distance,
    polygon_from_geojson,
    vertex_count,
)
from frontend.download_format import format_size
from frontend.gkonsol import text
from frontend.gkonsol.command import Command, Registry
from frontend.gkonsol.commands.common import (
    YES,
    confirm,
    find_dataset,
    to_date,
    to_float,
    to_int,
    to_metres,
)
from frontend.gkonsol.commands.earth_engine import complete_dataset
from frontend.gkonsol.effects import Ask, task
from frontend.gkonsol.parser import Args, Option, UsageError, tokenize
from frontend.gkonsol.ports import Context
from frontend.gkonsol.text import Span

GROUP = "Parameters"
MAX_SCALE = 100_000
NO_ANALYSIS = "none"
STOP_WORDS = ("q", "quit", "stop", ":q")

# The form's fields, as named in validation results.
LABELS = {
    "dataset": "Dataset", "bands": "Bands", "scale": "Scale", "max_cloud_cover": "Cloud cover",
    "composite": "Composite", "aoi": "Area", "dates": "Dates", "crs": "Projection",
    "output_dir": "Save to", "analysis_type": "Analysis", "processes": "Processes",
}
# The command that fixes each field.
FIXES = {
    "dataset": "form set dataset <KEY>", "bands": "form set bands <BAND>...", "scale": "form set scale <METRES>",
    "max_cloud_cover": "form set cloud <PERCENT>", "composite": "form set composite <METHOD>",
    "aoi": "form aoi bbox <W> <S> <E> <N>  (or circle / file)", "dates": "form set dates <START> <END>",
    "crs": "form set crs EPSG:4326", "output_dir": "form set output <FOLDER>",
    "analysis_type": "form set analysis <TYPE> <PROCESS>...", "processes": "form set processes <PROCESS>...",
}
CRS_WORDS = {
    "epsg:4326": "EPSG:4326", "4326": "EPSG:4326", "wgs84": "EPSG:4326", "wgs": "EPSG:4326",
    "utm": AUTO_UTM, "auto": AUTO_UTM, "auto_utm": AUTO_UTM,
    "epsg:3857": "EPSG:3857", "3857": "EPSG:3857", "mercator": "EPSG:3857", "web-mercator": "EPSG:3857",
}


# ----------------------------------------------------------------------------- showing the form
def _dataset(ctx: Context) -> DatasetInfo:
    info = get_dataset(ctx.form.current().dataset)
    if info is None:
        raise UsageError("Choose a dataset first: form set dataset <KEY>")
    return info


def area_text(form: FormDTO) -> str:
    """"Lahore (Polygon, 4 vertices) · lon 74.2000 → 74.4500, lat 31.4000 → 31.6000"."""
    try:
        geometry = json.loads(form.aoi)
        west, south, east, north = bbox_of(geometry)
        shape = f"{geometry['type']}, {vertex_count(geometry)} vertices"
    except (ValueError, KeyError, TypeError, IndexError):
        return f"{form.aoi_name or 'Area'} (unreadable GeoJSON)"
    return (f"{form.aoi_name or 'Area'} ({shape}) · lon {west:.4f} → {east:.4f}, "
            f"lat {south:.4f} → {north:.4f}")


def form_pairs(form: FormDTO) -> list[tuple[str, Any]]:
    info = get_dataset(form.dataset)
    if form.max_cloud_cover is not None:
        cloud: Any = f"at most {form.max_cloud_cover} %"
    else:
        cloud = Span(f"no filter{f' ({info.name} has none)' if info and not info.supports_cloud_filter else ''}",
                     text.MUTED)
    if form.start_date and form.end_date:
        days = (form.end_date - form.start_date).days + 1
        dates: Any = f"{form.start_date.isoformat()} → {form.end_date.isoformat()}  ({days} day{'s' if days != 1 else ''})"
    else:
        dates = Span("not set", text.WARNING)
    crs_label = dict(CRS_OPTIONS).get(form.crs, form.crs)
    if form.analysis_type:
        analysis: Any = f"{form.analysis_type}: {', '.join(form.processes) or 'no process chosen'}"
    else:
        analysis = Span("none (download only)", text.MUTED)
    return [
        ("Dataset", Span(f"{form.dataset}  ({info.name})" if info else form.dataset or "not chosen",
                         text.ACCENT if info else text.WARNING)),
        ("Bands", ", ".join(form.bands) if form.bands else Span("none chosen", text.WARNING)),
        ("Scale", f"{form.scale} m / pixel" if form.scale else Span("not set", text.WARNING)),
        ("Cloud cover", cloud),
        ("Composite", form.composite),
        ("Area", area_text(form) if form.aoi else Span("not chosen: form aoi bbox | circle | file", text.WARNING)),
        ("Dates", dates),
        ("Projection", crs_label),
        ("Save to", form.output_dir or Span("not chosen", text.WARNING)),
        ("Analysis", analysis),
    ]


def _show(ctx: Context, args: Args) -> None:
    form = ctx.form.current()
    if args.flag("json"):
        data = form.to_dict()
        if data.get("aoi"):
            data["aoi"] = json.loads(data["aoi"])
        ctx.out.text(json.dumps(data, indent=2, default=str))
        return
    ctx.out.heading("Parameter form")
    ctx.out.pairs(form_pairs(form))


# ----------------------------------------------------------------------------- setting fields
@dataclass(frozen=True)
class Field:
    name: str
    params: str
    help: str
    apply: Callable[[Context, list[str]], str]      # sets the field; returns what was done
    values: Optional[Callable[[Context, list[str]], list[str]]] = None  # Tab completion
    aliases: tuple[str, ...] = ()


def _one(values: list[str], field: str, params: str) -> str:
    if len(values) != 1:
        raise UsageError(f"'form set {field}' takes one value: {params}.")
    return values[0]


def _set_dataset(ctx: Context, values: list[str]) -> str:
    info = find_dataset(_one(values, "dataset", "KEY"))
    ctx.form.set_dataset(info.key)
    return (f"dataset = {info.key} ({info.name}). Bands, scale, cloud cover and composite are now "
            "its defaults.")


def _set_bands(ctx: Context, values: list[str]) -> str:
    info = _dataset(ctx)
    words = [word for value in values for word in value.replace(",", " ").split()]
    if not words:
        raise UsageError(f"Name at least one band of {info.name}: {' '.join(info.bands)}")
    if words == ["default"]:
        bands = list(info.default_bands)
    elif words == ["all"]:
        bands = list(info.bands)
    else:
        by_name = {band.lower(): band for band in info.bands}
        unknown = [word for word in words if word.lower() not in by_name]
        if unknown:
            raise UsageError(f"{info.name} has no band {', '.join(unknown)}. Its bands: {' '.join(info.bands)}")
        bands = list(dict.fromkeys(by_name[word.lower()] for word in words))
    ctx.form.set_bands(bands)
    return f"bands = {', '.join(ctx.form.current().bands)}"  # as the form holds them (in the dataset's order)


def _set_scale(ctx: Context, values: list[str]) -> str:
    word = _one(values, "scale", "METRES").lower().removesuffix("m")
    metres = to_int(word, "The scale (metres per pixel)", 1, MAX_SCALE)
    ctx.form.set_scale(metres)
    return f"scale = {metres} m / pixel"


def _set_cloud(ctx: Context, values: list[str]) -> str:
    info = _dataset(ctx)
    if not info.supports_cloud_filter:
        raise UsageError(f"{info.name} has no cloud-cover filter.")
    percent = to_int(_one(values, "cloud", "PERCENT").rstrip("%"), "The cloud cover", 0, 100)
    ctx.form.set_cloud_cover(percent)
    return f"cloud cover = at most {percent} %"


def _set_composite(ctx: Context, values: list[str]) -> str:
    method = _one(values, "composite", "METHOD").lower()
    if method not in COMPOSITE_METHODS:
        raise UsageError(f"The composite is one of: {', '.join(COMPOSITE_METHODS)}.")
    ctx.form.set_composite(method)
    return f"composite = {method}"


def _check_dates(info: DatasetInfo, start: date, end: date) -> None:
    if start > end:
        raise UsageError("The start date must be on or before the end date.")
    if end > date.today():
        raise UsageError("The end date cannot be in the future.")
    if start < info.min_date:
        raise UsageError(f"{info.name} starts on {info.min_date.isoformat()}.")
    if info.max_date is not None and end > info.max_date:
        raise UsageError(f"{info.name} ends on {info.max_date.isoformat()}.")


def _set_dates(ctx: Context, values: list[str]) -> str:
    if len(values) != 2:
        raise UsageError("'form set dates' takes two dates: START END, e.g. 2024-06-01 2024-08-31.")
    return _apply_dates(ctx, to_date(values[0], "The start date"), to_date(values[1], "The end date"))


def _set_start(ctx: Context, values: list[str]) -> str:
    current = ctx.form.current()
    return _apply_dates(ctx, to_date(_one(values, "start", "DATE"), "The start date"), current.end_date or date.today())


def _set_end(ctx: Context, values: list[str]) -> str:
    current = ctx.form.current()
    end = to_date(_one(values, "end", "DATE"), "The end date")
    return _apply_dates(ctx, current.start_date or end, end)


def _apply_dates(ctx: Context, start: date, end: date) -> str:
    _check_dates(_dataset(ctx), start, end)
    ctx.form.set_dates(start, end)
    return f"dates = {start.isoformat()} → {end.isoformat()}"


def _set_crs(ctx: Context, values: list[str]) -> str:
    word = _one(values, "crs", "EPSG:4326 | utm | EPSG:3857")
    code = CRS_WORDS.get(word.lower())
    if code is None:
        raise UsageError("The projection is EPSG:4326 (WGS 84), utm (the AOI's UTM zone) or EPSG:3857 (Web Mercator).")
    ctx.form.set_crs(code)
    return f"projection = {dict(CRS_OPTIONS)[code]}"


def _set_output(ctx: Context, values: list[str]) -> str:
    if not values:
        raise UsageError("Give the folder to save downloads in, e.g. form set output \"D:\\GEE data\".")
    folder = Path(" ".join(values)).expanduser()
    if not folder.is_absolute():
        raise UsageError("Use a full folder path, e.g. D:\\GEE-Assist\\downloads.")
    if folder.exists() and not folder.is_dir():
        raise UsageError(f"{folder} is a file, not a folder.")
    ctx.form.set_output_dir(str(folder))
    return f"save to = {folder}" + ("" if folder.exists() else "  (created when the download starts)")


def _analysis_name(info: DatasetInfo, word: str) -> str:
    for name in ANALYSIS_CATEGORIES:
        if name.lower() == word.lower():
            if name not in info.supported_analyses:
                supported = ", ".join(info.supported_analyses) or "none"
                raise UsageError(f"{info.name} does not support {name} analysis. Supported: {supported}.")
            return name
    raise UsageError(f"The analysis is none, {', '.join(ANALYSIS_CATEGORIES)}.")


def _processes(info: DatasetInfo, analysis: str, words: Sequence[str]) -> list[str]:
    supported = info.supported_analyses.get(analysis, ())
    by_name = {process.lower(): process for process in ANALYSIS_CATEGORIES[analysis]}
    chosen = []
    for word in (w for value in words for w in value.replace(",", " ").split()):
        process = by_name.get(word.lower())
        if process is None:
            raise UsageError(f"{analysis} has no process {word}. Its processes: {', '.join(ANALYSIS_CATEGORIES[analysis])}.")
        if process not in supported:
            raise UsageError(f"{info.name} cannot compute {process}. It can: {', '.join(supported)}.")
        chosen.append(process)
    return list(dict.fromkeys(chosen))


def _set_analysis(ctx: Context, values: list[str]) -> str:
    if not values:
        raise UsageError(f"Name the analysis: none, {', '.join(ANALYSIS_CATEGORIES)}.")
    info = _dataset(ctx)
    if values[0].lower() == NO_ANALYSIS:
        ctx.form.set_analysis("", [])
        return "analysis = none (download only)"
    analysis = _analysis_name(info, values[0])
    processes = _processes(info, analysis, values[1:])
    if not processes:  # keep the processes already chosen for it, if any
        current = ctx.form.current()
        processes = current.processes if current.analysis_type == analysis else []
    ctx.form.set_analysis(analysis, processes)
    if not processes:
        return (f"analysis = {analysis}. Now choose its processes: form set processes "
                f"{' '.join(info.supported_analyses[analysis])}")
    return f"analysis = {analysis}: {', '.join(processes)}"


def _set_processes(ctx: Context, values: list[str]) -> str:
    current = ctx.form.current()
    if not current.analysis_type:
        raise UsageError("Choose the analysis first: form set analysis <TYPE> [PROCESS...]")
    processes = _processes(_dataset(ctx), current.analysis_type, values)
    if not processes:
        raise UsageError("Name at least one process.")
    ctx.form.set_analysis(current.analysis_type, processes)
    return f"processes = {', '.join(processes)}"


# Tab completion of field values.
def _band_values(ctx: Context, typed: list[str]) -> list[str]:
    info = get_dataset(ctx.form.current().dataset)
    return ["default", "all", *info.bands] if info else []


def _analysis_values(ctx: Context, typed: list[str]) -> list[str]:
    info = get_dataset(ctx.form.current().dataset)
    if info is None:
        return []
    if not typed:
        return [NO_ANALYSIS, *info.supported_analyses]
    for name, processes in info.supported_analyses.items():
        if name.lower() == typed[0].lower():
            return list(processes)
    return []


def _process_values(ctx: Context, typed: list[str]) -> list[str]:
    form = ctx.form.current()
    info = get_dataset(form.dataset)
    return list(info.supported_analyses.get(form.analysis_type, ())) if info else []


FIELDS: tuple[Field, ...] = (
    Field("dataset", "KEY", "The satellite dataset (see 'datasets list'); its defaults fill the other fields",
          _set_dataset, lambda ctx, typed: [] if typed else complete_dataset(ctx, [], "")),
    Field("bands", "BAND...", "Bands to download, or 'default' or 'all'", _set_bands, _band_values),
    Field("scale", "METRES", "Pixel size in metres", _set_scale),
    Field("cloud", "PERCENT", "Leave out scenes cloudier than this (optical datasets)", _set_cloud,
          aliases=("cloud-cover", "clouds")),
    Field("composite", "METHOD", f"How images are combined: {', '.join(COMPOSITE_METHODS)}", _set_composite,
          lambda ctx, typed: [] if typed else list(COMPOSITE_METHODS)),
    Field("dates", "START END", "Time range, YYYY-MM-DD", _set_dates),
    Field("start", "DATE", "Start date, YYYY-MM-DD", _set_start),
    Field("end", "DATE", "End date, YYYY-MM-DD", _set_end),
    Field("crs", "EPSG:4326|utm|EPSG:3857", "Projection of the GeoTIFF", _set_crs,
          lambda ctx, typed: [] if typed else ["EPSG:4326", "utm", "EPSG:3857"], aliases=("projection",)),
    Field("output", "FOLDER", "Folder the download is saved in", _set_output, aliases=("folder", "save-to")),
    Field("analysis", "TYPE [PROCESS...]", "none, or Water, Vegetation, LST or LULC with its processes",
          _set_analysis, _analysis_values),
    Field("processes", "PROCESS...", "Processes of the chosen analysis, e.g. NDVI EVI", _set_processes,
          lambda ctx, typed: _process_values(ctx, typed)),
)


def _field(name: str) -> Field:
    for field in FIELDS:
        if name.lower() in (field.name, *field.aliases):
            return field
    raise UsageError(f"The form has no field '{name}'. Fields: {', '.join(field.name for field in FIELDS)}.")


def _set(ctx: Context, args: Args) -> None:
    field = _field(args.words[0])
    ctx.out.success(field.apply(ctx, args.words[1:]))


def _complete_set(ctx: Context, typed: list[str], prefix: str) -> list[str]:
    if not typed:
        return [field.name for field in FIELDS]
    try:
        field = _field(typed[0])
    except UsageError:
        return []
    return field.values(ctx, typed[1:]) if field.values else []


# ----------------------------------------------------------------------------- area of interest
def _area_show(ctx: Context, args: Args) -> None:
    form = ctx.form.current()
    if not form.aoi:
        ctx.out.muted("No area chosen. Set one with: form aoi bbox | circle | file | geojson")
        return
    ctx.out.print(Span("Area  ", text.MUTED), area_text(form))
    _estimate_line(ctx)


def _set_area(ctx: Context, geometry: dict, name: str, from_file: bool = False) -> None:
    ctx.form.set_area(json.dumps(geometry), name, from_file=from_file)
    ctx.out.success(f"area = {area_text(ctx.form.current())}")
    _estimate_line(ctx)


def _bbox(ctx: Context, args: Args) -> None:
    west, south, east, north = _bbox_values(args.words)
    _set_area(ctx, bbox_polygon(west, south, east, north), "Rectangle")


def _bbox_values(words: Sequence[str]) -> tuple[float, float, float, float]:
    if len(words) != 4:
        raise UsageError("A rectangle is four numbers: WEST SOUTH EAST NORTH (degrees).")
    west, east = (to_float(word, name, -180, 180) for word, name in ((words[0], "West"), (words[2], "East")))
    south, north = (to_float(word, name, -90, 90) for word, name in ((words[1], "South"), (words[3], "North")))
    if west >= east or south >= north:
        raise UsageError("West must be less than east, and south less than north.")
    return west, south, east, north


def _circle(ctx: Context, args: Args) -> None:
    lon, lat, radius = _circle_values(args.words)
    _set_area(ctx, circle_polygon(lon, lat, radius), f"Circle (r = {format_distance(radius)})")


def _circle_values(words: Sequence[str]) -> tuple[float, float, float]:
    if len(words) != 3:
        raise UsageError("A circle is: LON LAT RADIUS, e.g. 74.33 31.52 5km.")
    radius = to_metres(words[2])
    if radius > 500_000:
        raise UsageError("The radius can be at most 500 km.")
    return to_float(words[0], "The longitude", -180, 180), to_float(words[1], "The latitude", -90, 90), radius


def _file(ctx: Context, args: Args) -> Generator:
    if not args.words:
        raise UsageError("Give the GeoJSON file, e.g. form aoi file \"D:\\areas\\lahore.geojson\".")
    yield from _import_file(ctx, " ".join(args.words))


def _import_file(ctx: Context, path: str) -> Generator:
    geojson = yield task(ctx.facade.import_aoi, path, label="Reading the GeoJSON file")
    _set_area(ctx, json.loads(geojson), Path(path).name, from_file=True)


def _geojson(ctx: Context, args: Args) -> None:
    _set_area(ctx, _geometry(args.raw), "GeoJSON from gkonsol")


def _geometry(raw: str) -> dict:
    try:
        geometry = polygon_from_geojson(raw)
    except (ValueError, AttributeError) as exc:
        raise UsageError(f"That is not GeoJSON: {exc}") from None
    if geometry.get("type") not in ("Polygon", "MultiPolygon") or not geometry.get("coordinates"):
        raise UsageError("The GeoJSON must be a Polygon or MultiPolygon (or a Feature holding one).")
    return geometry


def _area_clear(ctx: Context, args: Args) -> None:
    ctx.form.clear_area()
    ctx.out.success("area cleared")


def _area_from_words(ctx: Context, words: list[str]) -> Generator:
    """The wizard's area answer: "bbox W S E N", "circle LON LAT RADIUS" or "file PATH"."""
    kind, rest = words[0].lower(), words[1:]
    if kind in ("bbox", "rect", "rectangle"):
        _set_area(ctx, bbox_polygon(*_bbox_values(rest)), "Rectangle")
    elif kind == "circle":
        lon, lat, radius = _circle_values(rest)
        _set_area(ctx, circle_polygon(lon, lat, radius), f"Circle (r = {format_distance(radius)})")
    elif kind == "file" and rest:
        yield from _import_file(ctx, " ".join(rest))
    else:
        raise UsageError("Type: bbox W S E N, circle LON LAT RADIUS, or file PATH.")


# ----------------------------------------------------------------------------- checking and keeping
def print_validation(ctx: Context, result: ValidationDTO) -> None:
    for key, message in result.errors.items():
        ctx.out.error(f"{LABELS.get(key, key)}: {message}")
        if key in FIXES:
            ctx.out.hint(FIXES[key])


def _validate(ctx: Context, args: Args) -> None:
    result = ctx.facade.check_form(ctx.form.current())
    if result.is_valid:
        ctx.out.success("All parameters are valid.")
        ctx.out.hint("form submit  keeps them as a request you can download")
    else:
        print_validation(ctx, result)


def _estimate_line(ctx: Context) -> None:
    estimate = estimate_for(ctx)
    if estimate:
        ctx.out.muted(f"  ≈ {estimate['size']} in {estimate['chunks']}  ·  'form estimate' for more")


def estimate_for(ctx: Context) -> Optional[dict[str, str]]:
    form = ctx.form.current()
    if not form.aoi or not form.bands or not form.scale:
        return None
    try:
        geometry = json.loads(form.aoi)
    except ValueError:
        return None
    estimate = estimate_download(
        geometry, form.scale, len(form.bands), BYTES_PER_PIXEL,
        GEE_MAX_REQUEST_BYTES * BYTES_PER_PIXEL // GEE_REQUEST_BYTES_PER_PIXEL, GEE_MAX_GRID_DIMENSION,
    )
    chunk_mb = ctx.facade.get_chunk_size_mb()
    chunks = max(1, math.ceil(estimate.total_bytes / (chunk_mb * BYTES_PER_MB)))
    return {
        "pixels": f"{estimate.width_px:,} × {estimate.height_px:,} px",
        "bands": str(len(form.bands)),
        "size": format_size(estimate.total_bytes),
        "chunks": f"{chunks} chunk{'s' if chunks != 1 else ''} of {chunk_mb} MB",
        "requests": f"{estimate.requests:,} (GEE allows {format_size(GEE_MAX_REQUEST_BYTES)} per request)",
    }


def _estimate(ctx: Context, args: Args) -> None:
    estimate = estimate_for(ctx)
    if estimate is None:
        raise UsageError("The estimate needs an area and at least one band.")
    ctx.out.pairs([("Grid", estimate["pixels"]), ("Bands", estimate["bands"]),
                   ("Size", f"about {estimate['size']} (float32 GeoTIFF)"), ("Chunks", estimate["chunks"]),
                   ("GEE requests", estimate["requests"])])


def _submit(ctx: Context, args: Args) -> None:
    result = ctx.form.submit()
    if not result.is_valid:
        print_validation(ctx, result)
        return
    number = len(ctx.facade.get_kept_requests())
    ctx.out.success(f"Parameters accepted and kept as request #{number}.")
    ctx.out.hint(f"download start {number}  downloads it")


def _reset(ctx: Context, args: Args) -> Generator:
    if not (yield from confirm("Reset every field of the parameter form?", args.flag("yes"))):
        ctx.out.muted("The form is unchanged.")
        return
    ctx.form.reset()
    ctx.out.success("The form is reset to its defaults.")


# ----------------------------------------------------------------------------- the wizard
def _wizard(ctx: Context, args: Args) -> Generator:
    ctx.out.heading("Fill the parameter form, step by step")
    ctx.out.muted("Press Enter to keep the value in [brackets]; Tab completes; type q to stop.")
    steps: list[tuple[str, Callable[[FormDTO], str], Optional[Field], tuple[str, ...]]] = [
        ("Dataset", lambda f: f.dataset, _field("dataset"), tuple(complete_dataset(ctx, [], ""))),
        ("Bands", lambda f: " ".join(f.bands), _field("bands"), ()),
        ("Scale in metres", lambda f: str(f.scale or ""), _field("scale"), ()),
        ("Max cloud cover %", lambda f: str(f.max_cloud_cover), _field("cloud"), ()),
        ("Composite", lambda f: f.composite, _field("composite"), COMPOSITE_METHODS),
        ("Start date", lambda f: f.start_date.isoformat() if f.start_date else "", _field("start"), ()),
        ("End date", lambda f: f.end_date.isoformat() if f.end_date else "", _field("end"), ()),
        ("Area: bbox W S E N | circle LON LAT RADIUS | file PATH", lambda f: f.aoi_name, None, ("bbox", "circle", "file")),
        ("Projection: EPSG:4326 | utm | EPSG:3857", lambda f: f.crs, _field("crs"), ("EPSG:4326", "utm", "EPSG:3857")),
        ("Save to folder", lambda f: f.output_dir, _field("output"), ()),
        ("Analysis: none | TYPE PROCESS...", lambda f: " ".join([f.analysis_type, *f.processes]) or NO_ANALYSIS,
         _field("analysis"), ()),
    ]
    for label, current, field, choices in steps:
        form = ctx.form.current()
        if field is not None and field.name == "cloud":
            info = get_dataset(form.dataset)
            if info is None or not info.supports_cloud_filter:
                continue
        if field is not None and field.name == "analysis":
            info = get_dataset(form.dataset)
            choices = (NO_ANALYSIS, *(info.supported_analyses if info else ()))
        if field is not None and field.name == "bands":
            choices = tuple(_band_values(ctx, []))
        while True:
            shown = current(form)
            answer = (yield Ask(f"{label} [{shown or 'none'}]:", choices=tuple(choices))).strip()
            if answer.lower() in STOP_WORDS:
                ctx.out.muted("Stopped. The values entered so far stay in the form.")
                return
            if not answer:
                break
            try:
                words = tokenize(answer)
                if field is None:
                    yield from _area_from_words(ctx, words)
                else:
                    ctx.out.success(field.apply(ctx, words))
                break
            except (UsageError, GeeAssistError) as exc:  # e.g. a GeoJSON file that cannot be read
                ctx.out.error(str(exc))
    ctx.out.blank()
    ctx.out.pairs(form_pairs(ctx.form.current()))
    result = ctx.facade.check_form(ctx.form.current())
    if not result.is_valid:
        print_validation(ctx, result)
        ctx.out.muted("Fix these with 'form set' (or run 'form wizard' again), then 'form submit'.")
        return
    if (yield from confirm("Submit these parameters now?", default=True)):
        _submit(ctx, Args())
    else:
        ctx.out.muted("Not submitted. 'form submit' keeps them later.")


# ----------------------------------------------------------------------------- natural language
def _ask(ctx: Context, args: Args) -> Generator:
    query = args.raw.strip()
    if not query:
        raise UsageError("Describe the data you need, e.g. ask NDVI of Lahore for summer 2024 from Sentinel-2")
    form = yield task(ctx.facade.submit_query, query, label="Asking Gemini")
    filled = ctx.form.apply(form)
    recognised = list(dict.fromkeys(entity.text for entity in form.entities))
    if recognised:
        ctx.out.print(Span("Recognised: ", text.MUTED), " · ".join(recognised))
    if not filled:
        ctx.out.warning(form.clarification or "No form values could be taken from that request. "
                                              "Try naming a place, dates or a dataset.")
        return
    ctx.out.success(f"Filled: {', '.join(filled)}.")
    for note in form.notes:
        ctx.out.muted(note)
    if form.clarification:
        ctx.out.warning(f"Gemini asks: {form.clarification}")
    ctx.out.pairs(form_pairs(ctx.form.current()))
    ctx.out.hint("Check the values (form set ... changes one), then: form submit")


def register(registry: Registry) -> None:
    form = registry.add(Command(
        "form", "Fill and submit the parameter form", _show, aliases=("params",), group=GROUP,
        options=[Option("json", "Show the parameters as JSON")],
        description="These commands fill the parameter form on the Query Input page: what you set here shows\n"
                    "there too. 'form' alone is 'form show'.",
    ))
    form.add(Command(
        "show", "Show the values in the form", _show, options=[Option("json", "Show them as JSON")],
        examples=[("form show", "Every field"), ("form show --json", "As JSON")],
    ))
    form.add(Command(
        "set", "Set one field of the form", _set, params="FIELD VALUE...", min_args=1, max_args=None,
        completer=_complete_set,
        description="Fields:\n" + "\n".join(f"  {field.name.ljust(10)} {field.params.ljust(24)} {field.help}"
                                             for field in FIELDS),
        examples=[
            ("form set dataset landsat8_l2", "Landsat 8, with its default bands and scale"),
            ("form set bands B4 B8", "Only the red and near-infrared bands"),
            ("form set dates 2024-06-01 2024-08-31", "Summer 2024"),
            ("form set cloud 10", "Leave out scenes more than 10 % cloudy"),
            ("form set output \"D:\\GEE data\"", "Save downloads there (quotes for spaces)"),
            ("form set analysis Vegetation NDVI EVI", "Compute NDVI and EVI"),
        ],
    ))
    aoi = form.add(Command(
        "aoi", "Set the area of interest", _area_show, aliases=("area",),
        description="'form aoi' alone shows the area. Coordinates are WGS 84 degrees; a negative number is\n"
                    "a coordinate, not an option.",
    ))
    aoi.add(Command("show", "Show the area", _area_show))
    aoi.add(Command(
        "bbox", "A rectangle: WEST SOUTH EAST NORTH", _bbox, params="W S E N", min_args=4, max_args=4,
        aliases=("rect", "rectangle"),
        examples=[("form aoi bbox 74.20 31.40 74.45 31.60", "Around Lahore"),
                  ("form aoi bbox -74.05 40.68 -73.90 40.82", "Manhattan: negative numbers work")],
    ))
    aoi.add(Command(
        "circle", "A circle: centre and radius", _circle, params="LON LAT RADIUS", min_args=3, max_args=3,
        examples=[("form aoi circle 73.08 31.42 10km", "10 km around Faisalabad")],
    ))
    aoi.add(Command(
        "file", "Import a GeoJSON file", _file, params="PATH", min_args=1, max_args=None,
        examples=[("form aoi file \"D:\\areas\\punjab.geojson\"", "Quotes keep spaces in paths")],
    ))
    aoi.add(Command(
        "geojson", "Paste a GeoJSON Polygon or MultiPolygon", _geojson, params="JSON", raw=True,
        examples=[('form aoi geojson {"type":"Polygon","coordinates":[[[73,31],[73.1,31],[73.1,31.1],[73,31]]]}',
                   "A triangle")],
    ))
    aoi.add(Command("clear", "Remove the area", _area_clear))
    form.add(Command("validate", "Check the form without keeping it", _validate, aliases=("check",)))
    form.add(Command("estimate", "Estimate the download's size, chunks and GEE requests", _estimate))
    form.add(Command(
        "wizard", "Fill the form step by step, answering questions", _wizard, aliases=("fill",),
        description="Asks for each field in turn, showing its value in [brackets]: press Enter to keep it.\n"
                    "Wrong answers are explained and asked again; q stops. At the end the form is checked\n"
                    "and you can submit it.",
    ))
    form.add(Command(
        "submit", "Check the form and keep it as a request", _submit,
        description="The same as Submit Parameters: the request appears under Kept Requests and\n"
                    "'download start' can download it.",
    ))
    form.add(Command("reset", "Put every field back to its default", _reset, options=[YES]))

    registry.add(Command(
        "ask", "Describe a request in plain words; Gemini fills the form", _ask, params="TEXT", raw=True,
        aliases=("gemini", "nl"), group=GROUP,
        description="The same as 'Chat with Gemini': the request is read for a place, dates, a dataset and an\n"
                    "analysis, and the form is filled with what was understood. Quotes are not needed.",
        examples=[("ask NDVI of Lahore for summer 2024 from Sentinel-2", "Fills dataset, area, dates and analysis"),
                  ("ask water bodies near Mangla Dam in 2023", "A water analysis")],
    ))
