"""gkonsol's app commands: open, sidebar, fullscreen, theme, panel, config, doctor and quit."""

from types import SimpleNamespace

import pytest

from backend.auth_exceptions import SessionExpiredError
from backend.config.download_settings import DownloadSettings
from backend.dto import CheckDTO
from frontend.gkonsol.commands import app as app_commands
from tests.gkonsol_fakes import terminal, user

SETTINGS = SimpleNamespace(auth_api_url="http://localhost:8000", auth_api_timeout=15.0, session_duration=7 * 86400,
                           gee_project="my-project")


@pytest.fixture
def term(monkeypatch, tmp_path):
    monkeypatch.setattr(app_commands, "get_settings", lambda: SETTINGS)
    monkeypatch.setattr(app_commands, "load_llm_settings", lambda: SimpleNamespace(api_key="key", model="gemini-x"))
    monkeypatch.setattr(app_commands, "DownloadSettingsStore",
                        lambda: SimpleNamespace(load=lambda: DownloadSettings(chunk_size_mb=500, retry_limit=3)))
    # The free space of this computer's drives does not matter here.
    monkeypatch.setattr(app_commands.shutil, "disk_usage", lambda path: SimpleNamespace(free=500_000_000_000))
    term = terminal()
    term.form.set_output_dir(str(tmp_path / "downloads"))
    return term


# ------------------------------------------------------------------ the window
def test_open_pages(term):
    assert "Showing Downloads." in term.type("open downloads")
    term.type("goto form")
    assert term.app.page == "query"
    assert "There is no page 'settings'" in term.type("open settings")
    assert term.shell.complete("open d")[1] == ["dashboard", "downloads"]


def test_the_prompt_follows_the_page(term):
    term.type("open account")
    assert term.type("whoami").startswith("ayesha@gkonsol ~/account $ whoami")


def test_side_bar_and_full_screen(term):
    term.type("sidebar")
    assert term.app.side_bar is True
    term.type("sidebar off")
    assert term.app.side_bar is False
    term.type("fullscreen on")
    assert term.app.full_screen is True
    assert "on, off or toggle" in term.type("fullscreen sideways")


def test_theme_lists_and_switches_after_asking(term):
    printed = term.type("theme")
    assert "● light" in printed and "(current)" in printed and "dark-green" in printed
    term.type("theme dark-grey")
    assert "restarts to use the Dark – grey theme" in term.shell.runner.asking.prompt
    term.type("y")
    assert ("theme", "dark-grey") in term.app.calls
    assert "already uses" in term.type("theme light")
    assert "There is no theme 'pink'" in term.type("theme pink")


def test_panel_size(term):
    assert "280 px" in term.type("panel")
    term.type("panel max")
    assert term.panel.maximized
    term.type("panel compress")
    assert not term.panel.maximized
    assert "400 px high" in term.type("panel height 400px")
    assert "from 80 to 4000" in term.type("panel height 10")


# ------------------------------------------------------------------ settings and check-up
def test_config_shows_the_settings(term):
    printed = term.type("config")
    assert "http://localhost:8000  (AUTH_API_URL)" in printed and "my-project" in printed
    assert "7 d 0 h  (SESSION_DURATION)" in printed and "gemini-x" in printed and "set" in printed
    assert "500 MB" in printed and ".env" in printed


def test_doctor_when_everything_works(term):
    term.facade.is_server_available.return_value = True
    term.facade.reload_current_user.return_value = user()
    term.facade.check_gee_setup.return_value = [CheckDTO("Connection", "ok", "Connected.")]
    printed = term.type("doctor")
    assert "✓ Authentication server" in printed and "✓ Session" in printed and "✓ Gemini" in printed
    assert "✓ Download folder" in printed and "free)" in printed and "Earth Engine" in printed
    assert printed.endswith("✓ Everything works.")


def test_doctor_reports_problems(term, monkeypatch):
    monkeypatch.setattr(app_commands, "load_llm_settings", lambda: SimpleNamespace(api_key="", model="m"))
    term.facade.is_server_available.return_value = True
    term.facade.reload_current_user.side_effect = SessionExpiredError("Your session has expired.", 401)
    term.facade.check_gee_setup.return_value = [CheckDTO("Connection", "fail", "Not signed in.")]
    printed = term.type("checkup")
    assert "✗ Session" in printed and "! Gemini" in printed and "✗ Connection" in printed
    assert printed.endswith("✗ 2 problems found, 1 warning.")


def test_doctor_without_the_server_skips_the_session(term):
    term.facade.is_server_available.return_value = False
    term.facade.check_gee_setup.return_value = []
    printed = term.type("doctor")
    assert "Cannot reach http://localhost:8000" in printed and "Session" not in printed
    term.facade.reload_current_user.assert_not_called()


def test_folder_check_warns_about_low_space(tmp_path, monkeypatch):
    monkeypatch.setattr(app_commands.shutil, "disk_usage", lambda path: SimpleNamespace(free=1_000_000_000))
    check = app_commands._folder_check(tmp_path / "new" / "folder")
    assert check.status == "warn" and "1.0 GB free" in check.detail


def test_quit_asks_first(term):
    term.type("quit")
    term.type("n")
    assert ("quit",) not in term.app.calls
    term.type("quit -y")
    assert ("quit",) in term.app.calls
