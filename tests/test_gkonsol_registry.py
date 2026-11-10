"""Every gkonsol command is registered, described and has a help page."""

import pytest

from frontend.gkonsol import help as help_pages
from frontend.gkonsol import text
from frontend.gkonsol.commands import build_registry

REGISTRY = build_registry()
ALL = list(REGISTRY.walk())


def test_the_groups_in_help_order():
    assert list(REGISTRY.groups()) == ["General", "Account", "Earth Engine", "Parameters", "Downloads", "App"]


def test_top_level_commands():
    assert [command.name for command in REGISTRY.commands()] == [
        "help", "clear", "history", "echo", "version", "exit",
        "whoami", "user", "session", "signout", "users", "server",
        "gee", "datasets",
        "form", "ask",
        "requests", "download",
        "open", "sidebar", "fullscreen", "theme", "panel", "config", "doctor", "quit",
    ]


@pytest.mark.parametrize("command", ALL, ids=[command.path for command in ALL])
def test_every_command_is_described_and_has_a_help_page(command):
    assert command.summary and not command.summary.endswith(".")
    assert command.handler is not None or command.subcommands
    page = "\n".join(text.plain(line) for line in help_pages.command_help(command, is_admin=True))
    assert page.startswith(f"{command.path} — {command.summary}") and command.usage in page


def test_only_users_and_its_subcommands_are_for_administrators():
    assert {command.path for command in ALL if command.needs_admin()} == {
        "users", "users list", "users show", "users role", "users enable", "users disable", "users open"}


def test_examples_name_real_commands():
    for command in ALL:
        for example, _ in command.examples:
            words = example.split()
            if words[0].startswith("!"):
                continue  # history references
            found, _ = REGISTRY.resolve(words)
            assert found is not None, example


def test_the_overview_hides_admin_commands_from_users():
    overview = "\n".join(text.plain(line) for line in help_pages.overview(REGISTRY, is_admin=False))
    assert "  users " not in overview and "  download " in overview
