"""The saved theme choice."""

import pytest

from frontend import appearance


def test_no_choice_yet_means_light(tmp_path):
    path = tmp_path / "appearance.json"
    assert appearance.saved_theme(path) is None
    assert appearance.current_theme(path) == "light"


@pytest.mark.parametrize("name", ["light", "dark-green", "dark-grey"])
def test_choice_is_saved(tmp_path, name):
    path = tmp_path / "workspace" / "appearance.json"
    appearance.save_theme(name, path)
    assert appearance.saved_theme(path) == name and appearance.current_theme(path) == name


def test_unknown_or_damaged_settings_count_as_no_choice(tmp_path):
    path = tmp_path / "appearance.json"
    path.write_text('{"theme": "neon"}', encoding="utf-8")
    assert appearance.saved_theme(path) is None
    path.write_text("not json", encoding="utf-8")
    assert appearance.saved_theme(path) is None
    path.write_text("[1, 2]", encoding="utf-8")
    assert appearance.saved_theme(path) is None


def test_unknown_theme_cannot_be_saved(tmp_path):
    with pytest.raises(ValueError):
        appearance.save_theme("neon", tmp_path / "appearance.json")
