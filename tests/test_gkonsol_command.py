"""gkonsol command definitions and the registry."""

import pytest

from frontend.gkonsol.command import Command, Registry
from frontend.gkonsol.parser import Option


def _registry() -> Registry:
    registry = Registry()
    download = registry.add(Command("download", "Downloads", aliases=("dl",), group="Downloads"))
    download.add(Command("start", "Start a download", handler=lambda ctx, args: None, params="[REQUEST]",
                         options=[Option("detach", short="d")], max_args=1))
    download.add(Command("list", "List downloads", aliases=("ls",)))
    registry.add(Command("users", "Manage users", admin=True, group="Account"))
    registry.add(Command("whoami", "Who is signed in", group="Account"))
    return registry


def test_commands_are_found_by_name_or_alias():
    registry = _registry()
    assert registry.find("download") is registry.find("dl")
    assert registry.find("nope") is None


def test_resolve_walks_down_the_subcommands():
    registry = _registry()
    command, used = registry.resolve(["dl", "ls", "--all"])
    assert command.path == "download list" and used == 2
    command, used = registry.resolve(["download", "3"])
    assert command.path == "download" and used == 1
    assert registry.resolve(["what"]) == (None, 0) and registry.resolve([]) == (None, 0)


def test_usage_lines_are_built_from_the_definition():
    registry = _registry()
    assert registry.find("download").usage == "download <subcommand>"
    assert registry.find("download").subcommand("start").usage == "download start [REQUEST] [options]"


def test_admin_commands_are_hidden_from_other_users():
    registry = _registry()
    assert "users" not in registry.names(is_admin=False) and "users" in registry.names()
    assert list(registry.groups(is_admin=False)) == ["Downloads", "Account"]
    assert [c.name for c in registry.groups(is_admin=False)["Account"]] == ["whoami"]


def test_subcommands_of_an_admin_command_need_admin_too():
    users = Command("users", "Manage users", admin=True)
    show = users.add(Command("show", "Show a user"))
    assert show.needs_admin() and not Command("whoami", "").needs_admin()


def test_names_cannot_be_used_twice():
    registry = _registry()
    with pytest.raises(ValueError, match="dl"):
        registry.add(Command("dl", "Clash"))
    with pytest.raises(ValueError):
        registry.find("download").add(Command("listing", "Clash", aliases=("ls",)))


def test_mistyped_names_get_suggestions():
    assert _registry().suggest("dowload") == ["download"]
    assert _registry().suggest("user", is_admin=False) == []


def test_walk_visits_every_command():
    assert [c.path for c in _registry().walk()] == ["download", "download start", "download list", "users", "whoami"]
