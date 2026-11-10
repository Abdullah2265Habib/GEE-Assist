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
from frontend.gkonsol.history import GkonsolStore  # noqa: E402
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
def home(app, monkeypatch, tmp_path):
    monkeypatch.setattr(home_window, "MainWindow", StubQueryWorkspace)
    # The terminal keeps its history and height in a file of the test's own.
    monkeypatch.setattr(home_window, "GkonsolStore", lambda: GkonsolStore(tmp_path / "gkonsol.json"))
    facade = MagicMock(spec=IBusinessFacade)
    facade.list_downloads.return_value = []
    facade.get_chunk_size_mb.return_value = 500
    facade.get_current_user.return_value = _user()
    window = HomeWindow(facade, _user())
    yield window
    window.terminal.shutdown()
    window.deleteLater()


def test_opens_on_the_dashboard_with_a_greeting(home):
    assert home.current_page() is home.dashboard
    assert home.dashboard.greeting.text() == "Welcome, Ayesha"
    assert home.back_button.isHidden()
    assert not home.side_bar.is_expanded() and home.downloads_button.text() == ""  # collapsed: icons only


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


def test_collapsed_side_bar_shows_icons_only(home):
    home.side_bar.set_expanded(False, animate=False)
    assert home.downloads_button.text() == "" and home.query_input_button.text() == ""  # icons only
    assert home.profile.details.isHidden()
    home.side_bar.set_expanded(True, animate=False)
    assert home.downloads_button.text() == "Downloads" and home.query_input_button.text() == "Query Input"
    assert not home.profile.details.isHidden()


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


def test_view_menu_toggles_the_side_bar(home):
    item = home.menu_bar.toggle_side_bar
    assert not item.isChecked()  # the side bar starts collapsed

    item.trigger()
    assert home.side_bar.is_expanded() and item.isChecked()

    home.side_bar.set_expanded(False, animate=False)  # e.g. by clicking the logo
    assert not item.isChecked()


def test_view_menu_full_screen_and_back(home, monkeypatch):
    calls = []
    for name in ("showFullScreen", "showMaximized", "showNormal"):
        monkeypatch.setattr(home, name, lambda name=name: calls.append(name))
    monkeypatch.setattr(home, "isMaximized", lambda: True)

    home.menu_bar.full_screen.trigger()
    assert calls == ["showFullScreen"] and home.menu_bar.full_screen.isChecked()
    home.menu_bar.full_screen.trigger()
    assert calls == ["showFullScreen", "showMaximized"]  # back to how it was
    assert not home.menu_bar.full_screen.isChecked()


def test_options_menu_opens_the_chunk_size_setting(home, monkeypatch):
    from frontend.views import download_view

    asked = []
    monkeypatch.setattr(download_view.QInputDialog, "getInt", lambda *a, **k: asked.append(a[1]) or (500, False))
    home.menu_bar.chunk_size.trigger()
    assert asked == ["Chunk size"]  # the same dialog as the Downloads page's "Change…"


def test_manage_users_is_in_the_options_menu_for_administrators_only(home, monkeypatch):
    assert not home.menu_bar.manage_users.isVisible()  # a user
    home.set_user(_user("admin"))
    assert home.menu_bar.manage_users.isVisible()

    class FakeAdminDialog:
        opened = 0

        def __init__(self, facade, parent):
            self.session_expired = MagicMock()

        def show(self):
            FakeAdminDialog.opened += 1

        def raise_(self):
            pass

        def activateWindow(self):  # noqa: N802 (Qt API)
            pass

    monkeypatch.setattr(home_window, "UserAdminDialog", FakeAdminDialog)
    home.menu_bar.manage_users.trigger()
    assert FakeAdminDialog.opened == 1


def test_help_menu_shows_the_about_box(home, monkeypatch):
    shown = []
    monkeypatch.setattr(home_window.QMessageBox, "about", lambda parent, title, text: shown.append(title))
    home.menu_bar.about.trigger()
    assert shown == ["About GEE-Assist"]


@pytest.mark.parametrize("answer, restarted", [("Yes", True), ("No", False)])
def test_choosing_a_theme_saves_it_and_restarts(home, monkeypatch, answer, restarted):
    from PyQt6.QtWidgets import QMessageBox

    saved, restarts = [], []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: getattr(QMessageBox.StandardButton, answer))
    monkeypatch.setattr(home_window.appearance, "save_theme", saved.append)
    monkeypatch.setattr(home_window, "restart_app", lambda: restarts.append(True))

    home.menu_bar.theme_actions["dark-green"].trigger()

    assert (saved, bool(restarts)) == ((["dark-green"], True) if restarted else ([], False))
    if not restarted:  # cancelled: the theme in use stays ticked
        assert home.menu_bar.theme_actions["light"].isChecked()


def test_side_bar_offers_query_input_and_downloads_with_animated_icons(home):
    from frontend.widgets.side_icons import DownloadIcon, WritingIcon

    assert isinstance(home.query_input_button.icon_drawing, WritingIcon)
    assert isinstance(home.downloads_button.icon_drawing, DownloadIcon)
    items = home.side_bar._items
    assert items.indexOf(home.query_input_button) < items.indexOf(home.downloads_button)  # Query Input first

    home.query_input_button.click()
    assert isinstance(home.current_page(), StubQueryWorkspace)
    assert home.query_input_button.isHidden() and not home.downloads_button.isHidden()  # not its own page

    home.downloads_button.click()
    assert home.current_page() is home.downloads
    assert not home.query_input_button.isHidden() and home.downloads_button.isHidden()


# ------------------------------------------------------------------ terminal (gkonsol)
def _prompt_text(home) -> str:
    from PyQt6.QtGui import QTextDocument

    document = QTextDocument()
    document.setHtml(home.terminal.prompt.text())
    return document.toPlainText().replace("\xa0", " ")


def test_the_terminal_starts_hidden_below_the_pages(home):
    assert home.terminal_area.widget(0) is home.pages and home.terminal_area.widget(1) is home.terminal
    assert not home.terminal_area.is_terminal_visible()
    assert not home.terminal_button.isChecked() and not home.menu_bar.toggle_terminal.isChecked()


def test_the_terminal_is_in_the_side_bar_with_an_animated_icon(home):
    from frontend.widgets.side_icons import TerminalIcon

    assert home.terminal_button.parent() is home.side_bar
    assert isinstance(home.terminal_button.icon_drawing, TerminalIcon)
    home.side_bar.set_expanded(True, animate=False)
    assert home.terminal_button.text() == "Terminal"


def test_the_side_bar_button_opens_and_closes_the_terminal(home):
    home.show()
    home.terminal_button.click()
    assert home.terminal_area.is_terminal_visible()
    assert home.terminal_button.isChecked() and home.menu_bar.toggle_terminal.isChecked()
    home.terminal_button.click()
    assert not home.terminal_area.is_terminal_visible()
    assert not home.terminal_button.isChecked() and not home.menu_bar.toggle_terminal.isChecked()
    home.hide()


def test_view_menu_terminal_opens_and_closes_it(home):
    home.show()
    home.menu_bar.toggle_terminal.trigger()
    assert home.terminal_area.is_terminal_visible() and home.terminal_button.isChecked()
    home.menu_bar.toggle_terminal.trigger()
    assert not home.terminal_area.is_terminal_visible() and not home.terminal_button.isChecked()
    home.hide()


def test_terminal_commands_drive_the_window(home):
    home.terminal.shell.submit("open downloads")
    assert home.current_page() is home.downloads
    assert _prompt_text(home) == "ayesha@gkonsol ~/downloads $ "
    home.terminal.shell.submit("sidebar on")
    assert home.side_bar.is_expanded()
    home.terminal.shell.submit("open dashboard")
    assert home.current_page() is home.dashboard and _prompt_text(home) == "ayesha@gkonsol ~ $ "


def test_the_prompt_follows_pages_opened_with_the_mouse(home):
    home.show_account()
    assert _prompt_text(home) == "ayesha@gkonsol ~/account $ "


def test_signing_out_from_the_terminal(home):
    messages = []
    home.signed_out.connect(messages.append)
    home.terminal.shell.submit("signout -y")
    assert messages == ["You have been signed out."]


def test_exit_hides_the_terminal(home):
    home.show()
    home.toggle_terminal()
    home.terminal.shell.submit("exit")
    assert not home.terminal_area.is_terminal_visible() and not home.terminal_button.isChecked()
    home.hide()


def test_closing_the_window_stops_a_running_command(home):
    home.terminal.shell.submit("download speed")  # runs until Ctrl+C
    assert home.terminal.shell.running is not None
    home.close()
    assert home.terminal.shell.running is None


# ------------------------------------------------------------------ the Terminal menu
def test_terminal_menu_shows_the_terminal_in_step_with_the_side_bar_and_view_menu(home):
    home.show()
    home.menu_bar.show_terminal.trigger()
    assert home.terminal_area.is_terminal_visible()
    assert home.terminal_button.isChecked() and home.menu_bar.toggle_terminal.isChecked()
    home.terminal_button.click()  # closed from the side bar: the menu follows
    assert not home.menu_bar.show_terminal.isChecked() and not home.terminal_area.is_terminal_visible()
    home.hide()


def test_terminal_menu_maximises_and_clears(home):
    home.show()
    home.menu_bar.maximize_terminal.trigger()
    assert home.terminal_area.is_terminal_visible() and home.terminal_area.is_terminal_maximized()
    home.terminal.shell.submit("echo something")
    home.menu_bar.clear_terminal.trigger()
    assert home.terminal.view.toPlainText() == ""
    home.menu_bar.maximize_terminal.trigger()
    assert not home.terminal_area.is_terminal_maximized()
    home.hide()


def test_terminal_menu_offers_stop_only_while_a_command_runs(home):
    home.menu_bar.terminal_menu.aboutToShow.emit()
    assert not home.menu_bar.stop_command.isEnabled()
    home.terminal.shell.submit("download speed")  # runs until stopped
    home.menu_bar.terminal_menu.aboutToShow.emit()
    assert home.menu_bar.stop_command.isEnabled()
    home.menu_bar.stop_command.trigger()
    assert home.terminal.shell.running is None


def test_terminal_menu_ticks_maximise_when_the_header_button_maximised(home):
    home.show()
    home.toggle_terminal()
    home.terminal.maximize_button.click()
    home.menu_bar.terminal_menu.aboutToShow.emit()
    assert home.menu_bar.maximize_terminal.isChecked()
    home.hide()


def test_terminal_menu_commands_open_the_terminal_and_run_there(home):
    home.show()
    home.menu_bar.terminal_commands["download list"].trigger()
    assert home.terminal_area.is_terminal_visible()
    assert "ayesha@gkonsol ~ $ download list" in home.terminal.view.toPlainText()  # typed for you to see
    assert "No downloads yet." in home.terminal.view.toPlainText()
    home.hide()


def test_terminal_menu_commands_wait_for_a_question_to_be_answered(home):
    home.terminal.shell.submit("signout")  # asks "Sign out of GEE-Assist? [y/N]"
    signed_out = []
    home.signed_out.connect(signed_out.append)
    home.menu_bar.terminal_commands["help"].trigger()
    assert home.terminal.shell.runner.asking is not None and signed_out == []
    assert "'help' did not run" in home.terminal.view.toPlainText()
