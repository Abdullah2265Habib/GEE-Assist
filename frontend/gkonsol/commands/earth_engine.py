"""Earth Engine commands: gee (status, verify, login, project) and datasets (list, show)."""

from __future__ import annotations

import threading
from typing import Generator, Sequence

from backend.config import ANALYSIS_CATEGORIES, DATASETS, DatasetInfo
from backend.config.settings import get_settings
from backend.dto import CheckDTO
from backend.dto.check_dto import CHECK_FAIL, CHECK_OK, CHECK_SKIP, CHECK_WARN
from frontend.gkonsol import text
from frontend.gkonsol.command import Command, Registry
from frontend.gkonsol.commands.common import find_dataset, timed
from frontend.gkonsol.effects import Interrupted, task
from frontend.gkonsol.parser import Args, Option
from frontend.gkonsol.ports import Context
from frontend.gkonsol.text import Span

GROUP = "Earth Engine"
REGISTER_URL = "https://code.earthengine.google.com/register"

_MARKS = {
    CHECK_OK: (text.MARK_OK, text.SUCCESS),
    CHECK_WARN: (text.MARK_WARN, text.WARNING),
    CHECK_FAIL: (text.MARK_FAIL, text.ERROR),
    CHECK_SKIP: (text.MARK_SKIP, text.MUTED),
}


# ----------------------------------------------------------------------------- checks
def print_checks(ctx: Context, checks: Sequence[CheckDTO]) -> None:
    """One line per check, with how to fix the ones that did not pass."""
    width = max((len(check.name) for check in checks), default=0) + 2
    for check in checks:
        mark, style = _MARKS.get(check.status, (text.MARK_SKIP, text.MUTED))
        spans = [Span(f"{mark} ", style), Span(check.name.ljust(width), text.BOLD if check.passed else style),
                 Span(check.detail, text.MUTED if check.status == CHECK_SKIP else text.TEXT)]
        if check.duration_ms is not None and check.status != CHECK_SKIP:
            spans.append(Span(f"  ({check.duration_ms:.0f} ms)", text.MUTED))
        ctx.out.print(*spans)
        if check.status in (CHECK_WARN, CHECK_FAIL):
            if check.hint:
                ctx.out.hint(check.hint)
            if _about_signing_in(check):
                ctx.out.hint("Sign in from here: gee login")


def _about_signing_in(check: CheckDTO) -> bool:
    about = f"{check.name} {check.detail} {check.hint}".lower()
    return "sign-in" in check.name.lower() or "earthengine authenticate" in about


def _summary(ctx: Context, checks: Sequence[CheckDTO]) -> None:
    failed = [check for check in checks if check.status == CHECK_FAIL]
    if failed:
        ctx.out.error(f"{len(failed)} step{'s' if len(failed) != 1 else ''} failed: fix "
                      f"{'them' if len(failed) != 1 else 'it'}, then run 'gee verify' again.")
    else:
        ctx.out.success("Earth Engine is ready: datasets can be downloaded.")


def _verify(ctx: Context, args: Args) -> Generator:
    ctx.out.muted("Checking the Earth Engine set-up step by step…")
    checks = yield task(ctx.facade.check_gee_setup, label="Checking Earth Engine")
    print_checks(ctx, checks)
    _summary(ctx, checks)


def _status(ctx: Context, args: Args) -> Generator:
    available, elapsed = yield task(timed, ctx.facade.is_gee_available, label="Contacting Earth Engine")
    ctx.out.pairs([
        ("Project", get_settings().gee_project or Span("not set (GEE_PROJECT in .env)", text.ERROR)),
        ("Connection", Span(f"active  ({elapsed:.0f} ms)", text.SUCCESS) if available
         else Span("not available", text.ERROR)),
    ])
    if not available:
        ctx.out.hint("'gee verify' shows what is missing, step by step")


def _login(ctx: Context, args: Args) -> Generator:
    url = yield task(ctx.facade.begin_gee_sign_in, label="Starting the Earth Engine sign-in")
    ctx.out.print("Sign in to Google Earth Engine in your browser, with the Google account of your Cloud project.")
    if not args.flag("no-browser") and ctx.app.open_url(url):
        ctx.out.muted("Your browser should open now. If it does not, open this address:")
    else:
        ctx.out.muted("Open this address in a browser on this computer:")
    ctx.out.info(url)
    stop = threading.Event()
    try:
        path = yield task(ctx.facade.complete_gee_sign_in, stop.is_set, label="Waiting for you to sign in, in the browser")
    except Interrupted:
        stop.set()
        ctx.facade.cancel_gee_sign_in()
        ctx.out.muted("Sign-in cancelled.")
        return
    finally:
        stop.set()  # also when the terminal closes while waiting
    ctx.out.success(f"Signed in to Earth Engine. The sign-in is saved in {path}")
    checks = yield task(ctx.facade.check_gee_setup, label="Checking the connection")
    print_checks(ctx, checks)
    _summary(ctx, checks)


def _project(ctx: Context, args: Args) -> None:
    project = get_settings().gee_project
    if project:
        ctx.out.pairs([("Project", Span(project, text.ACCENT)), ("Set in", "GEE_PROJECT in .env")])
        ctx.out.hint("To use another project, change GEE_PROJECT in .env and restart GEE-Assist.")
    else:
        ctx.out.error("No Cloud project is set: GEE_PROJECT in .env is empty.")
        ctx.out.hint(f"Register a project for Earth Engine at {REGISTER_URL}, put its id in .env as "
                     "GEE_PROJECT=your-project-id and restart GEE-Assist.")


# ----------------------------------------------------------------------------- datasets
def _available(info: DatasetInfo) -> str:
    return f"{info.min_date.isoformat()} → {info.max_date.isoformat() if info.max_date else 'present'}"


def _datasets_list(ctx: Context, args: Args) -> None:
    category = (args.value("category") or "").lower()
    analysis = (args.value("analysis") or "").lower()
    shown = [info for info in DATASETS.values()
             if category in info.category.lower()
             and (not analysis or any(analysis == name.lower() for name in info.supported_analyses))]
    if not shown:
        ctx.out.muted("No dataset matches.")
        return
    rows = [[info.key, info.name, f"{info.default_scale} m", _available(info),
             "yes" if info.supports_cloud_filter else "—", ", ".join(info.supported_analyses) or "—"]
            for info in shown]
    ctx.out.table(["KEY", "NAME", "SCALE", "AVAILABLE", "CLOUD", "ANALYSES"], rows, align="llrlll",
                  styles=(text.ACCENT,))
    ctx.out.muted(f"{len(shown)} dataset{'s' if len(shown) != 1 else ''}  ·  'datasets show <KEY>' for bands "
                  "and analyses  ·  'form set dataset <KEY>' to use one")


def _datasets_show(ctx: Context, args: Args) -> None:
    info = find_dataset(args.words[0])
    bands = " ".join(f"{band}*" if band in info.default_bands else band for band in info.bands)
    ctx.out.heading(info.name)
    ctx.out.pairs([
        ("Key", Span(info.key, text.ACCENT)),
        ("Collection", info.collection_id),
        ("Category", info.category),
        ("Satellite", info.satellite or "—"),
        ("Scale", f"{info.default_scale} m / pixel"),
        ("Available", _available(info)),
        ("Cloud filter", f"yes ({info.cloud_property})" if info.supports_cloud_filter else "no"),
        ("Composite", f"{info.default_composite} by default"),
        ("Bands", bands),
    ])
    ctx.out.muted("    * chosen by default")
    if info.supported_analyses:
        ctx.out.print(Span("  Analyses", text.MUTED))
        for category, processes in info.supported_analyses.items():
            missing = [p for p in ANALYSIS_CATEGORIES.get(category, ()) if p not in processes]
            ctx.out.print(Span(f"    {category}: ", text.BOLD), ", ".join(processes),
                          Span(f"  (not {', '.join(missing)})" if missing else "", text.MUTED))
    else:
        ctx.out.print(Span("  Analyses      none: download only", text.MUTED))


def complete_dataset(ctx: Context, typed: list[str], prefix: str) -> list[str]:
    return list(DATASETS) if not typed else []


def register(registry: Registry) -> None:
    gee = registry.add(Command(
        "gee", "Google Earth Engine: connection, sign-in and set-up checks", _status, group=GROUP,
        description="'gee' alone is 'gee status'. Earth Engine needs a Cloud project (GEE_PROJECT in .env)\n"
                    "and a sign-in on this computer ('gee login').",
    ))
    gee.add(Command(
        "status", "Whether Earth Engine can be used now", _status,
        examples=[("gee status", "Project and connection")],
    ))
    gee.add(Command(
        "verify", "Check the Earth Engine sign-in and set-up step by step", _verify, aliases=("check", "auth"),
        description="Checks, in order: the Earth Engine library, the Cloud project (GEE_PROJECT), the saved\n"
                    "sign-in on this computer, the connection to Earth Engine and a test request.\n"
                    "Each step says what was found and, when it fails, how to fix it.",
        examples=[("gee verify", "Run every check"), ("gee auth", "The same")],
    ))
    gee.add(Command(
        "login", "Sign this computer in to Earth Engine in the browser", _login, aliases=("signin",),
        options=[Option("no-browser", "Only show the address to open, do not open the browser")],
        description="Does what 'earthengine authenticate' does, from inside GEE-Assist: your browser opens\n"
                    "Google's sign-in page, and when you allow access the sign-in is saved on this computer\n"
                    "(~/.config/earthengine/credentials). The connection is then checked. Ctrl+C cancels.",
        examples=[("gee login", "Sign in with the browser"), ("gee login --no-browser", "Show the address only")],
    ))
    gee.add(Command("project", "Show the Cloud project Earth Engine uses", _project))

    datasets = registry.add(Command(
        "datasets", "The satellite datasets that can be downloaded", _datasets_list, aliases=("ds",), group=GROUP,
        options=[Option("category", "Only this category, e.g. radar", value="TEXT"),
                 Option("analysis", "Only datasets that support it: Water, Vegetation, LST or LULC", value="TYPE")],
        description="'datasets' alone is 'datasets list'.",
    ))
    datasets.add(Command(
        "list", "List the datasets", _datasets_list, aliases=("ls",),
        options=[Option("category", "Only this category, e.g. radar or optical", value="TEXT"),
                 Option("analysis", "Only datasets that support it: Water, Vegetation, LST or LULC", value="TYPE")],
        examples=[("datasets list", "Every dataset"), ("datasets list --analysis LST", "Datasets with temperature")],
    ))
    datasets.add(Command(
        "show", "Show a dataset's bands, dates and analyses", _datasets_show, params="DATASET",
        min_args=1, max_args=1, completer=complete_dataset,
        examples=[("datasets show landsat8_l2", "Landsat 8"), ("datasets show s2", "Common names work too")],
    ))
