"""gkonsol's Earth Engine commands: gee status / verify / login / project, and datasets."""

from types import SimpleNamespace

import pytest

from backend.data.clients.gee_sign_in import GEESignInCancelled
from backend.dto import CheckDTO
from backend.exceptions import GEESetupError
from frontend.gkonsol.commands import earth_engine
from tests.gkonsol_fakes import terminal

ALL_GOOD = [
    CheckDTO("Earth Engine library", "ok", "earthengine-api 1.7.48"),
    CheckDTO("Cloud project (GEE_PROJECT)", "ok", "my-project"),
    CheckDTO("Sign-in on this computer", "ok", "Saved sign-in: C:/Users/me/.config/earthengine/credentials"),
    CheckDTO("Connection", "ok", "Connected with project 'my-project'.", duration_ms=812),
    CheckDTO("Test request", "ok", "Earth Engine answered in 230 ms.", duration_ms=230),
]
NOT_SIGNED_IN = [
    CheckDTO("Earth Engine library", "ok", "earthengine-api 1.7.48"),
    CheckDTO("Cloud project (GEE_PROJECT)", "ok", "my-project"),
    CheckDTO("Sign-in on this computer", "warn", "No saved Earth Engine sign-in.",
             "Sign in to Earth Engine on this computer (earthengine authenticate)."),
    CheckDTO("Connection", "fail", "Earth Engine is not signed in on this computer. Run `earthengine authenticate` once."),
    CheckDTO("Test request", "skip", "Needs a connection."),
]


@pytest.fixture
def term(monkeypatch):
    monkeypatch.setattr(earth_engine, "get_settings", lambda: SimpleNamespace(gee_project="my-project"))
    return terminal()


# ------------------------------------------------------------------ verify
def test_verify_prints_each_step(term):
    term.facade.check_gee_setup.return_value = ALL_GOOD
    printed = term.type("gee verify")
    assert "✓ Earth Engine library" in printed and "earthengine-api 1.7.48" in printed
    assert "✓ Connection" in printed and "(812 ms)" in printed
    assert printed.endswith("✓ Earth Engine is ready: datasets can be downloaded.")


def test_verify_says_how_to_fix_what_failed(term):
    term.facade.check_gee_setup.return_value = NOT_SIGNED_IN
    printed = term.type("gee auth")
    assert "! Sign-in on this computer" in printed and "✗ Connection" in printed and "– Test request" in printed
    assert "→ Sign in from here: gee login" in printed
    assert printed.endswith("✗ 1 step failed: fix it, then run 'gee verify' again.")


def test_status_shows_the_project_and_the_connection(term):
    term.facade.is_gee_available.return_value = True
    printed = term.type("gee")
    assert "my-project" in printed and "active" in printed
    term.facade.is_gee_available.return_value = False
    assert "'gee verify' shows what is missing" in term.type("gee status")


# ------------------------------------------------------------------ login
def test_login_opens_the_browser_and_checks_the_connection(term):
    term.facade.begin_gee_sign_in.return_value = "https://accounts.google.com/o/oauth2/auth?x=1"
    term.facade.complete_gee_sign_in.return_value = "C:/Users/me/.config/earthengine/credentials"
    term.facade.check_gee_setup.return_value = ALL_GOOD
    printed = term.type("gee login")
    assert ("open_url", "https://accounts.google.com/o/oauth2/auth?x=1") in term.app.calls
    assert "https://accounts.google.com/o/oauth2/auth?x=1" in printed
    assert "✓ Signed in to Earth Engine. The sign-in is saved in C:/Users/me/.config/earthengine/credentials" in printed
    assert printed.endswith("Earth Engine is ready: datasets can be downloaded.")
    stop = term.facade.complete_gee_sign_in.call_args.args[0]
    assert stop() is True  # the wait is told to stop once it is over


def test_login_without_the_browser(term):
    term.facade.begin_gee_sign_in.return_value = "https://accounts.google.com/x"
    term.facade.complete_gee_sign_in.return_value = "creds"
    term.facade.check_gee_setup.return_value = ALL_GOOD
    printed = term.type("gee login --no-browser")
    assert not [call for call in term.app.calls if call[0] == "open_url"]
    assert "Open this address in a browser" in printed


def test_ctrl_c_cancels_the_sign_in(term):
    term.facade.begin_gee_sign_in.return_value = "https://accounts.google.com/x"
    term.facade.complete_gee_sign_in.side_effect = GEESignInCancelled("cancelled")
    term.type("gee login", settle=False)
    term.scheduler.run_next()  # the sign-in begins; the command now waits for the browser
    assert term.shell.status().startswith("Waiting for you to sign in")
    term.shell.interrupt()
    assert "Sign-in cancelled." in term.output()
    term.facade.cancel_gee_sign_in.assert_called_once_with()
    term.scheduler.finish_tasks()  # the wait ends after Ctrl+C: ignored
    assert term.shell.running is None and "✗" not in term.output()


def test_a_failed_sign_in_is_reported(term):
    term.facade.begin_gee_sign_in.return_value = "https://accounts.google.com/x"
    term.facade.complete_gee_sign_in.side_effect = GEESetupError("Google did not sign you in to Earth Engine (access_denied).")
    assert "✗ Google did not sign you in to Earth Engine (access_denied)." in term.type("gee login")


def test_project(term, monkeypatch):
    assert "my-project" in term.type("gee project")
    monkeypatch.setattr(earth_engine, "get_settings", lambda: SimpleNamespace(gee_project=""))
    printed = term.type("gee project")
    assert "GEE_PROJECT in .env is empty" in printed and earth_engine.REGISTER_URL in printed


# ------------------------------------------------------------------ datasets
def test_datasets_list(term):
    printed = term.type("datasets")
    assert "KEY" in printed and "sentinel2_sr" in printed and "jrc_water_monthly" in printed
    assert "2017-03-28 → present" in printed


def test_datasets_list_filters(term):
    printed = term.type("ds ls --analysis LST")
    assert "landsat8_l2" in printed and "sentinel2_sr" not in printed
    assert "sentinel1_grd" in term.type("datasets --category radar")
    assert "No dataset matches." in term.type("datasets list --category nothing")


def test_datasets_show(term):
    printed = term.type("datasets show s2")
    assert "Sentinel-2 Surface Reflectance (L2A)" in printed and "COPERNICUS/S2_SR_HARMONIZED" in printed
    assert "B4*" in printed and "B1 " in printed and "Vegetation: NDVI, EVI, SAVI, GNDVI" in printed
    radar = term.type("datasets show sentinel1_grd")
    assert "Water: WaterBodyDetection, WaterAreaEstimation" in radar and "(not NDWI, MNDWI)" in radar


def test_datasets_show_completes_keys(term):
    assert term.shell.complete("datasets show landsat")[1] == ["landsat9_l2", "landsat8_l2", "landsat7_l2", "landsat5_l2"]


def test_datasets_show_unknown(term):
    assert "Unknown dataset 'spot6'" in term.type("datasets show spot6")
