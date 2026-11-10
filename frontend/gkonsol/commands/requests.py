"""Kept request commands: requests (list, show, download).

A request is kept when the parameter form is submitted (Submit Parameters, or
``form submit``). The Kept Requests list numbers them from 1, and so does gkonsol.
"""

from __future__ import annotations

from typing import Generator, Optional

from backend.dto import FormDTO
from frontend.gkonsol import text
from frontend.gkonsol.command import Command, Registry
from frontend.gkonsol.commands.common import to_int
from frontend.gkonsol.commands.form import form_pairs
from frontend.gkonsol.parser import Args, Option, UsageError
from frontend.gkonsol.ports import Context
from frontend.gkonsol.text import Span
from frontend.views.kept_requests_view import can_download

GROUP = "Downloads"


def find_request(ctx: Context, word: Optional[str]) -> tuple[int, FormDTO]:
    """A kept request by number ("2", "#2"); without one, the latest that can be downloaded."""
    kept = ctx.facade.get_kept_requests()
    if not kept:
        raise UsageError("No requests are kept yet. Fill the form, then 'form submit' (or press Submit Parameters).")
    if word is None or word.lower() in ("last", "latest"):
        for number in range(len(kept), 0, -1):
            if can_download(kept[number - 1]):
                return number, kept[number - 1]
        raise UsageError("None of the kept requests can be downloaded yet: submit the parameter form first.")
    number = to_int(word.lstrip("#"), "The request number", 1, len(kept))
    return number, kept[number - 1]


def _summary(form: FormDTO) -> tuple[str, str, str]:
    if form.source == "nl":
        return "query", form.query_text, ""
    period = f"{form.start_date} → {form.end_date}" if form.start_date and form.end_date else "—"
    return "form", f"{form.dataset} · {form.analysis_type or 'download only'}", period


def _list(ctx: Context, args: Args) -> None:
    kept = ctx.facade.get_kept_requests()
    if not kept:
        ctx.out.muted("No requests are kept yet. Fill the form, then 'form submit'.")
        return
    rows = []
    for number, form in enumerate(kept, start=1):
        source, about, period = _summary(form)
        ready = Span("yes", text.SUCCESS) if can_download(form) else Span("no", text.MUTED)
        rows.append([f"#{number}", source, about, period, form.aoi_name or "—", ready])
    ctx.out.table(["#", "FROM", "REQUEST", "DATES", "AREA", "DOWNLOADABLE"], rows, styles=(text.ACCENT,))
    ctx.out.muted("'requests show <N>' for its parameters  ·  'download start <N>' downloads it")


def _show(ctx: Context, args: Args) -> None:
    number, form = find_request(ctx, args.word(0))
    ctx.out.heading(f"Request #{number}" + ("  (natural-language query)" if form.source == "nl" else ""))
    if form.source == "nl":
        ctx.out.pairs([("Query", form.query_text)])
    ctx.out.pairs(form_pairs(form))
    if can_download(form):
        ctx.out.hint(f"download start {number}  downloads it")


def _download(ctx: Context, args: Args) -> Generator:
    from frontend.gkonsol.commands.downloads import start

    yield from start(ctx, args.word(0), args.flag("detach"))


def _complete_number(ctx: Context, typed: list[str], prefix: str) -> list[str]:
    return [str(number) for number in range(1, len(ctx.facade.get_kept_requests()) + 1)] if not typed else []


def register(registry: Registry) -> None:
    requests = registry.add(Command(
        "requests", "The kept requests (submitted parameter forms)", _list, aliases=("req", "kept"), group=GROUP,
        description="'requests' alone is 'requests list'. N is the request's number in the list.",
    ))
    requests.add(Command("list", "List the kept requests", _list, aliases=("ls",)))
    requests.add(Command("show", "Show a kept request's parameters", _show, params="[N]", max_args=1,
                         completer=_complete_number,
                         examples=[("requests show 2", "Request #2"), ("requests show", "The latest")]))
    requests.add(Command("download", "Download a kept request (as 'download start N')", _download, params="[N]",
                         max_args=1, completer=_complete_number,
                         options=[Option("detach", "Start it and return to the prompt", short="d")]))
