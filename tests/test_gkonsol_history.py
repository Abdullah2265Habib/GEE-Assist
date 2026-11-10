"""gkonsol's command history and its saved settings file."""

import pytest

from frontend.gkonsol.history import GkonsolStore, History
from frontend.gkonsol.parser import UsageError


@pytest.fixture
def store(tmp_path):
    return GkonsolStore(tmp_path / "workspace" / "gkonsol.json")


def test_commands_are_kept_between_sessions(store):
    history = History(store)
    history.add("gee verify")
    history.add("  download watch ")
    assert History(store).entries == ["gee verify", "download watch"]


def test_blank_lines_and_repeats_are_not_kept(store):
    history = History(store)
    for command in ("whoami", "", "whoami", "  "):
        history.add(command)
    assert history.entries == ["whoami"]


def test_only_the_latest_commands_are_kept(store):
    history = History(store, limit=3)
    for n in range(5):
        history.add(f"echo {n}")
    assert history.entries == ["echo 2", "echo 3", "echo 4"]
    assert History(store, limit=3).entries == ["echo 2", "echo 3", "echo 4"]


def test_clear_forgets_everything(store):
    history = History(store)
    history.add("whoami")
    history.clear()
    assert History(store).entries == []


def test_the_store_keeps_other_settings_next_to_the_history(store):
    store.update(panel_height=300)
    History(store).add("whoami")
    assert store.load() == {"panel_height": 300, "history": ["whoami"]}


def test_an_unreadable_store_counts_as_empty(store):
    store.path.parent.mkdir(parents=True)
    store.path.write_text("{ not json", encoding="utf-8")
    assert store.load() == {} and History(store).entries == []
    store.path.write_text("[1, 2]", encoding="utf-8")
    assert store.load() == {}


def test_history_without_a_store_lives_in_memory():
    history = History()
    history.add("whoami")
    assert history.entries == ["whoami"]


@pytest.fixture
def typed():
    history = History()
    for command in ("gee verify", "form show", "download start 2", "download watch"):
        history.add(command)
    return history


@pytest.mark.parametrize("line, expected", [
    ("!!", "download watch"),
    ("!! --all", "download watch --all"),
    ("!2", "form show"),
    ("!-2", "download start 2"),
    ("!gee", "gee verify"),
    ("!download", "download watch"),
    ("whoami", "whoami"),
    ("echo !!", "echo !!"),          # only a reference at the start is replaced
])
def test_references_name_earlier_commands(typed, line, expected):
    assert typed.expand(line) == expected


@pytest.mark.parametrize("line", ["!9", "!-9", "!0", "!nothing"])
def test_unknown_references_are_errors(typed, line):
    with pytest.raises(UsageError, match="no such command"):
        typed.expand(line)


def test_bang_bang_with_an_empty_history_is_an_error():
    with pytest.raises(UsageError):
        History().expand("!!")
