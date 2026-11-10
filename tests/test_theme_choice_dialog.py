"""Choosing a theme on the first start-up (no window on screen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication, QDialog  # noqa: E402

from frontend import appearance  # noqa: E402
from frontend.views import theme_choice_dialog as module  # noqa: E402
from frontend.views.theme_choice_dialog import ThemeChoiceDialog, ask_theme_on_first_run  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_offers_the_three_themes_with_light_selected(app):
    dialog = ThemeChoiceDialog()
    assert [option.text() for option in dialog.options.values()] == ["Light", "Dark – blue-green", "Dark – grey"]
    assert dialog.chosen_theme() == "light"
    dialog.options["dark-grey"].setChecked(True)
    assert dialog.chosen_theme() == "dark-grey"
    dialog.deleteLater()


def _answer(monkeypatch, theme, accepted=True):
    def fake_exec(dialog):
        dialog.options[theme].setChecked(True)
        return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    monkeypatch.setattr(module.ThemeChoiceDialog, "exec", fake_exec)


def test_first_run_light_is_saved_and_needs_no_restart(app, tmp_path, monkeypatch):
    path = tmp_path / "appearance.json"
    _answer(monkeypatch, "light")
    assert ask_theme_on_first_run(path) is False
    assert appearance.saved_theme(path) == "light"


def test_first_run_dark_is_saved_and_restarts_the_app(app, tmp_path, monkeypatch):
    path = tmp_path / "appearance.json"
    _answer(monkeypatch, "dark-green")
    assert ask_theme_on_first_run(path) is True  # the tests run in the light theme
    assert appearance.saved_theme(path) == "dark-green"


def test_closing_the_window_keeps_the_light_theme(app, tmp_path, monkeypatch):
    path = tmp_path / "appearance.json"
    _answer(monkeypatch, "dark-grey", accepted=False)
    assert ask_theme_on_first_run(path) is False
    assert appearance.saved_theme(path) == "light"


def test_not_asked_again_once_chosen(app, tmp_path, monkeypatch):
    path = tmp_path / "appearance.json"
    appearance.save_theme("dark-grey", path)
    monkeypatch.setattr(module.ThemeChoiceDialog, "exec", lambda dialog: pytest.fail("asked again"))
    assert ask_theme_on_first_run(path) is False
