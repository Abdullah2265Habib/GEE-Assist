"""The signed-in window opens on the dashboard and navigates between its pages."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtCore import pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMainWindow  # noqa: E402

from backend.business.facade import IBusinessFacade  # noqa: E402
from backend.dto import FormDTO  # noqa: E402
from backend.dto.user_dto import UserDTO  # noqa: E402
from frontend.views import home_window  # noqa: E402
from frontend.views.home_window import HomeWindow  # noqa: E402


class StubQueryWorkspace(QMainWindow):
    """Stands in for the parameter form, whose web map cannot start in a headless test run."""

    download_requested = pyqtSignal(object)

    def __init__(self, facade):
        super().__init__()


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _user(role: str = "user") -> UserDTO:
    return UserDTO(id="1", username="ayesha", full_name="Ayesha Khan", role=role)


@pytest.fixture
def home(app, monkeypatch):
    monkeypatch.setattr(home_window, "MainWindow", StubQueryWorkspace)
    facade = MagicMock(spec=IBusinessFacade)
    facade.list_downloads.return_value = []
    facade.get_chunk_size_mb.return_value = 500
    window = HomeWindow(facade, _user())
    yield window
    window.deleteLater()


def test_opens_on_the_dashboard_with_a_greeting(home):
    assert home.current_page() is home.dashboard
    assert home.dashboard.greeting.text() == "Welcome, Ayesha"
    assert home.dashboard_button.isHidden()


def test_query_input_button_opens_the_parameter_form(home):
    home.dashboard.query_tile.button.click()

    assert isinstance(home.current_page(), StubQueryWorkspace)
    assert not home.dashboard_button.isHidden()


def test_dashboard_button_returns_to_the_dashboard(home):
    home.show_query_input()
    home.dashboard_button.click()

    assert home.current_page() is home.dashboard


def test_account_page_is_reachable_from_the_header(home):
    home.account_button.click()

    assert home.current_page() is not home.dashboard
    assert home.account_button.isHidden()
    assert not home.dashboard_button.isHidden()


def test_unbuilt_workspaces_are_disabled_placeholders(home):
    grid = home.dashboard.findChildren(type(home.dashboard.query_tile))
    active = (home.dashboard.query_tile, home.dashboard.download_tile)
    placeholders = [tile for tile in grid if tile not in active]

    assert len(placeholders) == 2  # Analysis and Reports
    assert all(not tile.isEnabled() and tile.button is None for tile in placeholders)


def test_download_card_opens_the_downloads_page(home):
    home.dashboard.download_tile.button.click()

    assert home.current_page() is home.downloads
    assert home.downloads_button.isHidden() and not home.dashboard_button.isHidden()


def test_start_download_in_query_input_starts_the_job_and_shows_downloads(home, monkeypatch):
    started = []
    monkeypatch.setattr(home.downloads, "start", started.append)
    form = FormDTO(dataset="sentinel2_sr", aoi="{}")

    home.query_input.download_requested.emit(form)

    assert started == [form]
    assert home.current_page() is home.downloads
