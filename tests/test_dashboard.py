"""The signed-in window opens on the dashboard and navigates between its pages."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtCore import pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QPushButton  # noqa: E402

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
    assert home.back_button.isHidden()
    assert not home.side_bar.is_expanded() and home.downloads_button.text() == "D"  # side bar starts collapsed


def test_query_input_button_opens_the_parameter_form(home):
    home.dashboard.query_tile.button.click()

    assert isinstance(home.current_page(), StubQueryWorkspace)
    assert not home.back_button.isHidden()


def test_back_button_returns_from_query_input(home):
    home.show_query_input()
    home.back_button.click()

    assert home.current_page() is home.dashboard


def test_there_is_no_separate_dashboard_item(home):
    home.show_downloads()
    names = [button.text() for button in home.side_bar.findChildren(QPushButton) if button.isVisibleTo(home)]
    assert "Dashboard" not in names and "Db" not in names


def test_back_button_returns_to_the_dashboard(home):
    home.show_downloads()
    assert not home.back_button.isHidden()

    home.back_button.click()
    assert home.current_page() is home.dashboard and home.back_button.isHidden()


def test_dashboard_has_the_logo_at_the_top_and_no_home_icon(home):
    home.show()
    QApplication.processEvents()
    top_margin = home.side_bar.layout().contentsMargins().top()
    assert home.back_button.isHidden() and home.side_bar.logo.y() == top_margin
    assert "⌂" not in [label.text() for label in home.side_bar.findChildren(QLabel)]

    home.show_downloads()
    QApplication.processEvents()
    assert not home.back_button.isHidden() and home.side_bar.logo.y() > top_margin  # back button above it


def test_navigation_is_in_a_side_bar_without_the_app_name(home):
    texts = [label.text() for label in home.findChildren(QLabel)]
    assert "GEE-Assist" not in texts  # only the logo
    assert home.downloads_button.parent() is home.side_bar
    assert home.side_bar.logo.iconSize().width() == 64  # larger than the old 36 px header logo


def test_collapsed_side_bar_shows_short_labels(home):
    home.side_bar.set_expanded(False, animate=False)
    assert home.downloads_button.text() == "D"
    assert home.profile.details.isHidden()
    home.side_bar.set_expanded(True, animate=False)
    assert home.downloads_button.text() == "Downloads" and not home.profile.details.isHidden()


def test_collapsed_avatar_is_centred_under_the_logo(home):
    home.show()
    QApplication.processEvents()
    bar = home.side_bar
    avatar_centre = home.profile.avatar.mapTo(bar, home.profile.avatar.rect().center()).x()
    logo_centre = bar.logo.geometry().center().x()
    assert abs(avatar_centre - logo_centre) <= 1


def test_profile_menu_offers_the_account_options(home, monkeypatch):
    shown = []
    monkeypatch.setattr(home.account_menu, "popup", shown.append)
    home.profile.clicked.emit()

    assert len(shown) == 1
    names = [action.text() for action in home.account_menu.actions() if not action.isSeparator()]
    assert names == ["Manage account  (coming soon)", "View account", "Sign-up details", "Sign out"]
    assert not home.manage_account_action.isEnabled()


def test_sign_out_is_in_the_account_menu(home):
    messages = []
    home.signed_out.connect(messages.append)
    home.sign_out_action.trigger()

    assert messages == ["You have been signed out."]
    assert not [b for b in home.side_bar.findChildren(QPushButton) if b.text() in ("Sign out", "S")]


def test_view_account_opens_the_account_page(home):
    home.view_account_action.trigger()

    assert home.current_page() is not home.dashboard
    assert not home.back_button.isHidden()


def test_signup_details_open_for_the_signed_in_user(home, monkeypatch):
    opened = []
    monkeypatch.setattr(home_window.SignupDetailsDialog, "exec",
                        lambda dialog: opened.append(dialog.values["username"].text()))
    home.signup_details_action.trigger()
    assert opened == ["ayesha"]


def test_unbuilt_workspaces_are_disabled_placeholders(home):
    grid = home.dashboard.findChildren(type(home.dashboard.query_tile))
    active = (home.dashboard.query_tile, home.dashboard.download_tile)
    placeholders = [tile for tile in grid if tile not in active]

    assert len(placeholders) == 2  # Analysis and Reports
    assert all(not tile.isEnabled() and tile.button is None for tile in placeholders)


def test_download_card_opens_the_downloads_page(home):
    home.dashboard.download_tile.button.click()

    assert home.current_page() is home.downloads
    assert home.downloads_button.isHidden() and not home.back_button.isHidden()


def test_start_download_in_query_input_starts_the_job_and_shows_downloads(home, monkeypatch):
    started = []
    monkeypatch.setattr(home.downloads, "start", started.append)
    form = FormDTO(dataset="sentinel2_sr", aoi="{}")

    home.query_input.download_requested.emit(form)

    assert started == [form]
    assert home.current_page() is home.downloads


# ------------------------------------------------------------------ menu bar
def test_menu_bar_is_above_every_page(home):
    assert home.menuBar() is home.menu_bar
    for show in (home.show_dashboard, home.show_query_input, home.show_downloads, home.show_account):
        show()
        assert home.menu_bar.isVisibleTo(home)


def test_view_menu_switches_pages(home):
    bar = home.menu_bar
    bar.view_downloads.trigger()
    assert home.current_page() is home.downloads
    bar.view_query_input.trigger()
    assert isinstance(home.current_page(), StubQueryWorkspace)
    bar.view_account.trigger()
    assert home.current_page() is home._account_page
    bar.view_dashboard.trigger()
    assert home.current_page() is home.dashboard


def test_file_menu_new_request_sign_out_and_exit(home, monkeypatch):
    home.menu_bar.new_request.trigger()
    assert isinstance(home.current_page(), StubQueryWorkspace)

    messages = []
    home.signed_out.connect(messages.append)
    home.menu_bar.sign_out.trigger()
    assert messages == ["You have been signed out."]

    quits = []
    monkeypatch.setattr(home_window.QApplication, "quit", lambda: quits.append(True))
    home.menu_bar.exit.trigger()
    assert quits == [True]
