"""General commands: help, clear, history, echo, version, exit."""

from __future__ import annotations

import platform
import sys
from importlib import metadata

from frontend.gkonsol import help as help_pages
from frontend.gkonsol import text
from frontend.gkonsol.command import Command, Registry
from frontend.gkonsol.parser import Args, Option, UsageError
from frontend.gkonsol.ports import Context
from frontend.gkonsol.text import Span

GROUP = "General"
GKONSOL_VERSION = "1.0"


# ----------------------------------------------------------------------------- help
def _help(ctx: Context, args: Args) -> None:
    registry: Registry = ctx.shell.registry
    if not args.words:
        ctx.out.lines(help_pages.overview(registry, ctx.is_admin))
        return
    command, used = registry.resolve(args.words)
    if command is None or used < len(args.words) or (command.needs_admin() and not ctx.is_admin):
        asked = " ".join(args.words)
        message = f"No help for '{asked}': it is not a gkonsol command."
        suggestions = registry.suggest(args.words[0], ctx.is_admin) if command is None else []
        if suggestions:
            message += " Did you mean " + " or ".join(f"'{s}'" for s in suggestions) + "?"
        raise UsageError(message)
    ctx.out.lines(help_pages.command_help(command, ctx.is_admin))


def _complete_help(ctx: Context, typed: list[str], prefix: str) -> list[str]:
    registry: Registry = ctx.shell.registry
    if not typed:
        return [command.name for command in registry.commands(ctx.is_admin)]
    command, used = registry.resolve(typed)
    if command is None or used < len(typed):
        return []
    return [sub.name for sub in command.subcommands if ctx.is_admin or not sub.needs_admin()]


# ----------------------------------------------------------------------------- the rest
def _clear(ctx: Context, args: Args) -> None:
    ctx.shell.clear()


def _history(ctx: Context, args: Args) -> None:
    history = ctx.shell.history
    if args.flag("clear"):
        history.clear()
        ctx.out.success("The command history is cleared.")
        return
    word = args.word(0)
    if word is not None and not word.isdigit():
        raise UsageError(f"'{word}' is not a number of commands.")
    entries = history.entries
    if not entries:
        ctx.out.muted("No commands yet.")
        return
    first = max(0, len(entries) - (int(word) if word else 20))
    width = len(str(len(entries)))
    for number, entry in enumerate(entries[first:], start=first + 1):
        ctx.out.print(Span(f"{number:>{width}}  ", text.MUTED), entry)
    ctx.out.muted(f"Run one again with !<number> (e.g. !{len(entries)}), or the last one with !!.")


def _echo(ctx: Context, args: Args) -> None:
    ctx.out.print(args.raw)


def _version(ctx: Context, args: Args) -> None:
    from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR

    ctx.out.heading("GEE-Assist")
    ctx.out.pairs([
        ("gkonsol", GKONSOL_VERSION),
        ("Python", sys.version.split()[0]),
        ("PyQt / Qt", f"{PYQT_VERSION_STR} / {QT_VERSION_STR}"),
        ("Earth Engine API", _package_version("earthengine-api")),
        ("Gemini API", _package_version("google-genai")),
        ("System", platform.platform()),
    ])


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not installed"


def _exit(ctx: Context, args: Args) -> None:
    ctx.panel.close()


def register(registry: Registry) -> None:
    registry.add(Command(
        "help", "Show every command, or how to use one", _help, params="[COMMAND [SUBCOMMAND]]",
        aliases=("?",), group=GROUP, max_args=None, completer=_complete_help,
        examples=[("help", "List every command"), ("help download start", "How to start a download")],
    ))
    registry.add(Command(
        "clear", "Clear the terminal", _clear, aliases=("cls",), group=GROUP,
        description="Removes everything printed so far. Ctrl+L does the same.",
    ))
    registry.add(Command(
        "history", "Show the commands typed before", _history, params="[COUNT]", max_args=1, group=GROUP,
        options=[Option("clear", "Forget every command typed so far")],
        description="The history is kept between sessions. Press ↑ and ↓ to go through it, or run a command\n"
                    "again with !! (the last one), !<number>, !-<n> (n back) or !<start of the command>.",
        examples=[("history", "The last 20 commands"), ("history 50", "The last 50"),
                  ("!!", "Run the last command again"), ("!gee", "Run the last command starting with 'gee'")],
    ))
    registry.add(Command(
        "echo", "Print text", _echo, params="TEXT", raw=True, group=GROUP,
        examples=[("echo Hello from gkonsol", "Prints: Hello from gkonsol")],
    ))
    registry.add(Command(
        "version", "Show the versions of GEE-Assist and its libraries", _version, aliases=("about",), group=GROUP,
    ))
    registry.add(Command(
        "exit", "Hide the terminal", _exit, aliases=("close",), group=GROUP,
        description="The terminal keeps its output and history: open it again from the side bar or with Ctrl+`.",
    ))
