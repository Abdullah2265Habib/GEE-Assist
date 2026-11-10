"""docs/GKONSOL.md describes every gkonsol command and alias."""

from pathlib import Path

import pytest

from frontend.gkonsol.commands import build_registry

DOC = (Path(__file__).resolve().parents[1] / "docs" / "GKONSOL.md").read_text(encoding="utf-8")
COMMANDS = list(build_registry().walk())


def _synopsis(command) -> str:
    """The usage line without the generic parts: "download start [REQUEST]"."""
    usage = command.usage
    for generic in (" [options]", " <subcommand>", " [subcommand]"):
        usage = usage.replace(generic, "")
    return usage


@pytest.mark.parametrize("command", COMMANDS, ids=[command.path for command in COMMANDS])
def test_every_command_has_a_section(command):
    assert f"`{command.path}`" in DOC, f"docs/GKONSOL.md does not describe '{command.path}'"
    assert _synopsis(command) in DOC, f"docs/GKONSOL.md does not show the usage '{_synopsis(command)}'"


@pytest.mark.parametrize("command", [c for c in COMMANDS if c.aliases], ids=[c.path for c in COMMANDS if c.aliases])
def test_every_alias_is_listed(command):
    prefix = f"{command.parent.path} " if command.parent else ""
    for alias in command.aliases:
        assert f"`{prefix}{alias}`" in DOC, f"docs/GKONSOL.md does not list the alias '{prefix}{alias}'"


def test_the_doc_says_the_commands_only_work_inside_gee_assist():
    assert "gkonsol commands work only inside GEE-Assist" in DOC
    assert "PowerShell" in DOC and "Windows Terminal" in DOC


def test_every_terminal_menu_item_is_described():
    from frontend.widgets.menu_bar import TERMINAL_COMMANDS

    for items in TERMINAL_COMMANDS:
        for label, command in items:
            assert f"**{label.replace('&', '')}** | Runs `{command}`" in DOC, label
    for label in ("Show terminal", "Maximise terminal", "Clear terminal", "Stop running command", "Command reference"):
        assert f"| **{label}**" in DOC, label
