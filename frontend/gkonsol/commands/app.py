"""App commands: open, sidebar, fullscreen, theme, panel, config, doctor and quit."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Generator

from backend.auth_exceptions import AuthError
from backend.config import DEFAULT_DOWNLOAD_DIR
from backend.config.download_settings import DownloadSettingsStore
from backend.config.llm import load_llm_settings
from backend.config.settings import PROJECT_ROOT, get_settings
from backend.dto import CheckDTO
from backend.dto.check_dto import CHECK_FAIL, CHECK_OK, CHECK_WARN
from frontend import appearance, palette
from frontend.download_format import format_size
from frontend.gkonsol import text
from frontend.gkonsol.command import Command, Registry
from frontend.gkonsol.commands.common import SWITCH_WORDS, YES, confirm, duration, switch, timed, to_int
from frontend.gkonsol.commands.earth_engine import print_checks
from frontend.gkonsol.effects import task
from frontend.gkonsol.history import STORE_FILE
from frontend.gkonsol.parser import Args, UsageError
from frontend.gkonsol.ports import PAGES, Context
from frontend.gkonsol.text import Span

GROUP = "App"
LOW_DISK_BYTES = 5_000_000_000   # warn below 5 GB free
MIN_PANEL_HEIGHT = 110     # as low as the terminal panel goes (its header, a line and the prompt)

PAGE_WORDS = {
    "dashboard": "dashboard", "home": "dashboard",
    "query": "query", "query-input": "query", "form": "query", "parameters": "query",
    "downloads": "downloads", "download": "downloads",
    "account": "account", "profile": "account",
}


# ----------------------------------------------------------------------------- the window
def _open(ctx: Context, args: Args) -> None:
    page = PAGE_WORDS.get(args.words[0].lower())
    if page is None:
        raise UsageError(f"There is no page '{args.words[0]}'. Pages: {', '.join(PAGES)}.")
    ctx.app.show_page(page)
    ctx.out.muted(f"Showing {PAGES[page]}.")


def _side_bar(ctx: Context, args: Args) -> None:
    expanded = switch(args.word(0), ctx.app.is_side_bar_expanded())
    ctx.app.set_side_bar_expanded(expanded)
    ctx.out.muted(f"The side bar is {'open' if expanded else 'collapsed'}.")


def _full_screen(ctx: Context, args: Args) -> None:
    on = switch(args.word(0), ctx.app.is_full_screen())
    ctx.app.set_full_screen(on)
    ctx.out.muted(f"Full screen is {'on' if on else 'off'}. (F11 also switches it.)")


def _theme(ctx: Context, args: Args) -> Generator:
    if not args.words:
        for name, label in appearance.THEMES.items():
            current = name == palette.THEME
            ctx.out.print(Span("● " if current else "○ ", text.ACCENT if current else text.MUTED),
                          Span(name.ljust(12), text.ACCENT if current else text.TEXT), label,
                          Span("  (current)" if current else "", text.MUTED))
        ctx.out.hint("theme <name>  switches (GEE-Assist restarts)")
        return
    name = args.words[0].lower()
    if name not in appearance.THEMES:
        raise UsageError(f"There is no theme '{args.words[0]}'. Themes: {', '.join(appearance.THEMES)}.")
    if name == palette.THEME:
        ctx.out.muted(f"GEE-Assist already uses the {appearance.THEMES[name]} theme.")
        return
    question = (f"GEE-Assist restarts to use the {appearance.THEMES[name]} theme; a running download is paused "
                "and can be resumed. Restart now?")
    if not (yield from confirm(question, args.flag("yes"))):
        ctx.out.muted("The theme is unchanged.")
        return
    ctx.app.restart_with_theme(name)


def _panel(ctx: Context, args: Args) -> None:
    ctx.out.pairs([("Height", f"{ctx.panel.terminal_height()} px"),
                   ("Maximised", "yes" if ctx.panel.is_terminal_maximized() else "no")])
    ctx.out.muted("Drag the line above the terminal to resize it, or: panel max | panel restore | panel height <PX>")


def _panel_max(ctx: Context, args: Args) -> None:
    ctx.panel.set_terminal_maximized(True)


def _panel_restore(ctx: Context, args: Args) -> None:
    ctx.panel.set_terminal_maximized(False)


def _panel_height(ctx: Context, args: Args) -> None:
    pixels = to_int(args.words[0].lower().removesuffix("px"), "The height (pixels)", MIN_PANEL_HEIGHT, 4000)
    ctx.panel.set_terminal_height(pixels)
    ctx.out.muted(f"The terminal is {ctx.panel.terminal_height()} px high.")


# ----------------------------------------------------------------------------- settings
def _config(ctx: Context, args: Args) -> None:
    settings = get_settings()
    llm = load_llm_settings()
    downloads = DownloadSettingsStore().load()
    ctx.out.heading("Settings")
    ctx.out.pairs([
        ("Auth server", f"{settings.auth_api_url}  (AUTH_API_URL)"),
        ("Server timeout", f"{settings.auth_api_timeout:g} s  (AUTH_API_TIMEOUT)"),
        ("Keep signed in for", f"{duration(settings.session_duration)}  (SESSION_DURATION)"),
        ("Earth Engine project", settings.gee_project or Span("not set  (GEE_PROJECT)", text.WARNING)),
        ("Gemini model", f"{llm.model}  (GEMINI_MODEL)"),
        ("Gemini API key", Span("set", text.SUCCESS) if llm.api_key else Span("not set  (GEMINI_API_KEY)", text.WARNING)),
        ("Download folder", str(DEFAULT_DOWNLOAD_DIR)),
        ("Chunk size", f"{downloads.chunk_size_mb} MB"),
        ("Retries per chunk", str(downloads.retry_limit)),
        ("Theme", appearance.THEMES.get(palette.THEME, palette.THEME)),
    ])
    ctx.out.muted(f"Settings file: {PROJECT_ROOT / '.env'}  ·  gkonsol history: {STORE_FILE}")
    ctx.out.muted("Changes to .env take effect when GEE-Assist starts again.")


# ----------------------------------------------------------------------------- check-up
def _doctor(ctx: Context, args: Args) -> Generator:
    ctx.out.heading("GEE-Assist check-up")
    url = get_settings().auth_api_url
    checks: list[CheckDTO] = []

    reachable, elapsed = yield task(timed, ctx.facade.is_server_available, label="Contacting the authentication server")
    checks.append(CheckDTO("Authentication server", CHECK_OK, f"{url} answered.", duration_ms=elapsed) if reachable
                  else CheckDTO("Authentication server", CHECK_FAIL, f"Cannot reach {url}.",
                                "Start GEE-Assist-Backend, or set AUTH_API_URL in .env."))
    if reachable:
        try:
            user, elapsed = yield task(timed, ctx.facade.reload_current_user, label="Checking your session")
            checks.append(CheckDTO("Session", CHECK_OK, f"Signed in as {user.username}.", duration_ms=elapsed))
        except AuthError as exc:
            checks.append(CheckDTO("Session", CHECK_FAIL, str(exc), "Sign in again: signout"))
    checks.append(CheckDTO("Gemini", CHECK_OK, "GEMINI_API_KEY is set.") if load_llm_settings().api_key
                  else CheckDTO("Gemini", CHECK_WARN, "GEMINI_API_KEY is not set: 'ask' fills the form only from "
                                "what it recognises itself.", "Create a key at https://aistudio.google.com/apikey"))
    checks.append(_folder_check(Path(ctx.form.current().output_dir or DEFAULT_DOWNLOAD_DIR)))
    print_checks(ctx, checks)

    ctx.out.print(Span("Earth Engine", text.BOLD))
    gee = yield task(ctx.facade.check_gee_setup, label="Checking Earth Engine")
    print_checks(ctx, gee)

    problems = [check for check in checks + list(gee) if check.status == CHECK_FAIL]
    warnings = [check for check in checks + list(gee) if check.status == CHECK_WARN]
    if problems:
        ctx.out.error(f"{len(problems)} problem{'s' if len(problems) != 1 else ''} found"
                      + (f", {len(warnings)} warning{'s' if len(warnings) != 1 else ''}" if warnings else "") + ".")
    else:
        ctx.out.success("Everything works" + (f" ({len(warnings)} warning{'s' if len(warnings) != 1 else ''})."
                                              if warnings else "."))


def _folder_check(folder: Path) -> CheckDTO:
    name = "Download folder"
    existing = folder
    while not existing.exists() and existing.parent != existing:
        existing = existing.parent  # the folder is created when a download starts
    if not existing.exists() or not existing.is_dir():
        return CheckDTO(name, CHECK_FAIL, f"{folder} cannot be created.", "form set output <FOLDER>")
    if not os.access(existing, os.W_OK):
        return CheckDTO(name, CHECK_FAIL, f"{existing} is read-only.", "form set output <FOLDER>")
    free = shutil.disk_usage(existing).free
    detail = f"{folder}  ({format_size(free)} free)"
    if free < LOW_DISK_BYTES:
        return CheckDTO(name, CHECK_WARN, detail, "Large downloads may not fit: free some space or choose another drive.")
    return CheckDTO(name, CHECK_OK, detail)


def _quit(ctx: Context, args: Args) -> Generator:
    if not (yield from confirm("Quit GEE-Assist? A running download is paused and resumes next time.",
                               args.flag("yes"))):
        ctx.out.muted("Still running.")
        return
    ctx.app.quit()


def _complete_page(ctx: Context, typed: list[str], prefix: str) -> list[str]:
    return list(PAGES) if not typed else []


def _complete_switch(ctx: Context, typed: list[str], prefix: str) -> list[str]:
    return list(SWITCH_WORDS) if not typed else []


def register(registry: Registry) -> None:
    registry.add(Command(
        "open", "Show a page: dashboard, query, downloads or account", _open, params="PAGE", min_args=1, max_args=1,
        aliases=("goto",), group=GROUP, completer=_complete_page,
        examples=[("open downloads", "The Downloads page"), ("open query", "The parameter form")],
    ))
    registry.add(Command("sidebar", "Open or collapse the side bar", _side_bar, params="[on|off|toggle]",
                         max_args=1, group=GROUP, completer=_complete_switch))
    registry.add(Command("fullscreen", "Switch full screen on or off", _full_screen, params="[on|off|toggle]",
                         max_args=1, group=GROUP, completer=_complete_switch))
    registry.add(Command(
        "theme", "Show the themes, or switch to one", _theme, params="[NAME]", max_args=1, group=GROUP, options=[YES],
        completer=lambda ctx, typed, prefix: list(appearance.THEMES) if not typed else [],
        examples=[("theme", "List the themes"), ("theme dark-grey", "Switch (after asking)")],
    ))
    panel = registry.add(Command(
        "panel", "Resize the terminal panel", _panel, group=GROUP,
        description="The terminal sits below the page, like VS Code's. Drag the line above it to make it\n"
                    "taller or shorter, or use these. 'panel' alone shows its size.",
    ))
    panel.add(Command("max", "Make the terminal fill the window", _panel_max, aliases=("maximize", "expand")))
    panel.add(Command("restore", "Give the page its room back", _panel_restore, aliases=("compress", "normal")))
    panel.add(Command("height", "Set the terminal's height in pixels", _panel_height, params="PX",
                      min_args=1, max_args=1, examples=[("panel height 400", "400 pixels high")]))
    registry.add(Command("config", "Show the settings GEE-Assist runs with", _config, aliases=("settings",),
                         group=GROUP))
    registry.add(Command(
        "doctor", "Check everything: server, session, Gemini, download folder, Earth Engine", _doctor,
        aliases=("checkup",), group=GROUP,
        description="Runs every check gkonsol has and says how to fix what does not work.",
    ))
    registry.add(Command("quit", "Quit GEE-Assist", _quit, group=GROUP, options=[YES]))
