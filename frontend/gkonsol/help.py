"""The help pages, made from the command definitions.

``help`` lists every command by group; ``help <command>`` shows one command: its
usage, description, options, subcommands and examples.
"""

from __future__ import annotations

from pathlib import Path

from frontend.gkonsol import text
from frontend.gkonsol.command import Command, Registry
from frontend.gkonsol.text import Line, Span

INTRO = "gkonsol — the GEE-Assist command line"
NOT_A_SHELL = ("Its commands run inside GEE-Assist only: they are not Windows, PowerShell or cmd commands, "
               "and those do not work here.")
KEYS = ("Tab completes  ·  ↑ ↓ history  ·  Ctrl+C stops a command  ·  Ctrl+L clears  ·  "
        "Ctrl+` shows or hides the terminal")
# Every command, with examples: opened by Terminal → Command reference.
REFERENCE_FILE = Path(__file__).resolve().parents[2] / "docs" / "GKONSOL.md"


def overview(registry: Registry, is_admin: bool) -> list[Line]:
    lines: list[Line] = [[Span(INTRO, text.HEADING)], [Span(NOT_A_SHELL, text.MUTED)], []]
    groups = registry.groups(is_admin)
    width = max(len(command.name) for commands in groups.values() for command in commands) + 3
    for group, commands in groups.items():
        lines.append([Span(group, text.BOLD)])
        for command in commands:
            lines.append([Span("  " + command.name.ljust(width), text.ACCENT), Span(command.summary)])
        lines.append([])
    lines.append([Span("Type ", text.MUTED), Span("help <command>", text.INFO),
                  Span(" for its options and examples, e.g. ", text.MUTED), Span("help download", text.INFO), Span(".", text.MUTED)])
    lines.append([Span("Every command is described in docs/GKONSOL.md (Terminal → Command reference).", text.MUTED)])
    lines.append([Span(KEYS, text.MUTED)])
    return lines


def command_help(command: Command, is_admin: bool) -> list[Line]:
    lines: list[Line] = [[Span(command.path, text.HEADING), Span(f" — {command.summary}")]]
    if command.needs_admin():
        lines.append([Span("For administrators only.", text.WARNING)])
    lines += [[], [Span("Usage", text.BOLD)], [Span("  " + command.usage, text.INFO)]]
    if command.aliases:
        prefix = command.parent.path + " " if command.parent else ""
        names = ", ".join(prefix + alias for alias in command.aliases)
        lines.append([Span(f"  Also: {names}", text.MUTED)])
    if command.description:
        lines.append([])
        lines += [[Span(paragraph)] if paragraph else [] for paragraph in command.description.strip().split("\n")]
    subcommands = [sub for sub in command.subcommands if is_admin or not sub.needs_admin()]
    if subcommands:
        width = max(len(sub.name) for sub in subcommands) + 3
        lines += [[], [Span("Subcommands", text.BOLD)]]
        lines += [[Span("  " + sub.name.ljust(width), text.ACCENT), Span(sub.summary)] for sub in subcommands]
    if command.options:
        width = max(len(option.syntax()) for option in command.options) + 3
        lines += [[], [Span("Options", text.BOLD)]]
        lines += [[Span("  " + option.syntax().ljust(width), text.ACCENT), Span(option.help)]
                  for option in command.options]
    if command.examples:
        width = max(len(example) for example, _ in command.examples) + 3
        lines += [[], [Span("Examples", text.BOLD)]]
        lines += [[Span("  " + example.ljust(width), text.INFO), Span(about, text.MUTED)]
                  for example, about in command.examples]
    if subcommands:
        lines += [[], [Span(f"Type 'help {command.path} <subcommand>' for more about one.", text.MUTED)]]
    return lines
