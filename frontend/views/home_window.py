"""Window shown after signing in.

A menu bar along the top (File, Edit, View, Terminal, Options, Help) over a side bar on the
left (logo, navigation and the signed-in user) next to the pages: the dashboard (start
page), the query-input workspace, downloads, the account card and the GeoTIFF viewer
(opened from a finished download). Clicking the logo slides the side bar open or closed; clicking the user
opens the account menu (account options and "Sign out").

Below the pages is the terminal, gkonsol, as in VS Code: hidden until opened from the
side bar's Terminal button, the Terminal menu or View → Terminal (Ctrl+`), and as tall
as the user drags it. The Terminal menu also runs common commands in it.
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QCloseEvent, QDesktopServices, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.business.facade import IBusinessFacade
from backend.dto.user_dto import UserDTO
from frontend import appearance, theme
from frontend.views.account_view import AccountView, Avatar, SignupDetailsDialog
from frontend.restart import restart_app
from frontend.views.auth.hero_panel import round_logo
from frontend.views.dashboard_view import DashboardView
from frontend.views.download_view import DownloadView
from frontend.views.main_window import MainWindow
from frontend.views.raster_viewer_view import RasterViewerView
from frontend.gkonsol.form_port import WidgetForm
from frontend.gkonsol.help import REFERENCE_FILE
from frontend.gkonsol.history import GkonsolStore, History
from frontend.gkonsol.panel import GkonsolPanel, TerminalArea
from frontend.gkonsol.ports import MemoryForm
from frontend.views.user_admin_view import UserAdminDialog
from frontend.widgets.menu_bar import AppMenuBar
from frontend.widgets.side_bar import LOGO_SIZE, SideBar
from frontend.widgets.side_icons import DownloadIcon, TerminalIcon, WritingIcon

PAGE_BACKGROUND = (
    "qlineargradient(x1:0, y1:0, x2:1, y2:1, "
    f"stop:0 {theme.PAGE_GRADIENT_TOP}, stop:0.6 {theme.PAGE_GRADIENT_MIDDLE}, stop:1 {theme.PAGE_GRADIENT_BOTTOM})"
)

class ProfileButton(QFrame):
    """The signed-in user at the bottom of the side bar: avatar, plus name and role when expanded."""

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ProfileButton")
        self.setStyleSheet(
            f"#ProfileButton {{ border-radius: 8px; }} #ProfileButton:hover {{ background: {theme.FOAM}; }}"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Your account")
        self.avatar = Avatar(38)
        self.name = QLabel()
        self.name.setStyleSheet(f"color: {theme.INK}; font-weight: 600;")
        self.role = QLabel(objectName="Muted")
        for label in (self.name, self.role):  # clipped, not holding the bar open, while it slides
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        # Name and role in one widget: hidden, it takes no room, so the avatar can centre.
        self.details = QWidget()
        self.details.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        who = QVBoxLayout(self.details)
        who.setContentsMargins(0, 0, 0, 0)
        who.setSpacing(0)
        who.addWidget(self.name)
        who.addWidget(self.role)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(6, 6, 6, 6)
        self._row.setSpacing(10)
        self._row.addWidget(self.avatar)
        self._row.addWidget(self.details, 1)

    def set_user(self, user: UserDTO) -> None:
        self.avatar.set_user(user)
        self.name.setText(user.full_name)
        self.role.setText("Administrator" if user.is_admin else "User")

    def set_compact(self, compact: bool) -> None:
        self.details.setVisible(not compact)
        self._row.setAlignment(self.avatar, Qt.AlignmentFlag.AlignHCenter if compact else Qt.AlignmentFlag.AlignLeft)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class TerminalApp:
    """What gkonsol's commands can do in the signed-in window (its ``AppPort``)."""

    def __init__(self, window: "HomeWindow"):
        self._window = window

    def current_page(self) -> str:
        window = self._window
        pages = {window.dashboard: "dashboard", window.query_input: "query", window.downloads: "downloads",
                 window._account_page: "account"}
        return pages.get(window.current_page(), "dashboard")

    def show_page(self, page: str) -> None:
        window = self._window
        {"dashboard": window.show_dashboard, "query": window.show_query_input, "downloads": window.show_downloads,
         "account": window.show_account}[page]()

    def sign_out(self) -> None:
        self._window.sign_out()

    def is_side_bar_expanded(self) -> bool:
        return self._window.side_bar.is_expanded()

    def set_side_bar_expanded(self, expanded: bool) -> None:
        self._window.side_bar.set_expanded(expanded)

    def is_full_screen(self) -> bool:
        return self._window.isFullScreen()

    def set_full_screen(self, on: bool) -> None:
        self._window.set_full_screen(on)

    def restart_with_theme(self, theme_name: str) -> None:
        appearance.save_theme(theme_name)  # the terminal has asked already
        restart_app()

    def open_path(self, path: str) -> bool:
        return QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def open_url(self, url: str) -> bool:
        return QDesktopServices.openUrl(QUrl(url))

    def open_user_admin(self) -> None:
        self._window.open_user_admin()

    def quit(self) -> None:
        self._window.exit_app()


class HomeWindow(QMainWindow):
    signed_out = pyqtSignal(str)  # message for the sign-in screen

    def __init__(self, facade: IBusinessFacade, user: UserDTO, parent: QWidget | None = None):
        super().__init__(parent)
        self._facade = facade
        self._user = user
        self.setWindowTitle("GEE-Assist")
        self.setMinimumSize(1000, 680)

        # ---- side bar
        # ---- menu bar (File, Edit, View, ...) above every page
        self.menu_bar = AppMenuBar(self)
        self.setMenuBar(self.menu_bar)

        self.side_bar = SideBar(round_logo(LOGO_SIZE, self.devicePixelRatioF()))
        self.back_button = self.side_bar.back_button
        self.back_button.setToolTip("Back to the dashboard")
        self.query_input_button = self.side_bar.add_button("Query Input", "Q", icon=WritingIcon())
        self.downloads_button = self.side_bar.add_button("Downloads", "D", icon=DownloadIcon())
        self.terminal_button = self.side_bar.add_button("Terminal", "T", icon=TerminalIcon())
        self.terminal_button.setCheckable(True)  # lit while the terminal is open
        self.terminal_button.setToolTip("Terminal: gkonsol, the GEE-Assist command line (Ctrl+`)")
        self.manage_users = self.side_bar.add_button("Manage users", "M")
        self.manage_users.setToolTip("Administrators: view accounts, change roles, enable or disable users")
        self.profile = ProfileButton()
        self.side_bar.add_widget(self.profile, footer=True)

        # ---- account menu
        self.account_menu = QMenu(self)
        self.account_menu.setStyleSheet(theme.MENU_STYLE)
        self.manage_account_action = QAction("Manage account  (coming soon)", self)
        self.manage_account_action.setEnabled(False)
        self.view_account_action = QAction("View account", self)
        self.signup_details_action = QAction("Sign-up details", self)
        self.sign_out_action = QAction("Sign out", self)
        for action in (self.manage_account_action, self.view_account_action, self.signup_details_action):
            self.account_menu.addAction(action)
        self.account_menu.addSeparator()
        self.account_menu.addAction(self.sign_out_action)

        # ---- pages
        self.dashboard = DashboardView()

        # The query-input workspace (parameter form + kept requests) is a QMainWindow
        # of its own; shown as a page it is embedded as a plain widget.
        self.query_input = MainWindow(facade)
        self.query_input.setWindowFlags(Qt.WindowType.Widget)
        self.downloads = DownloadView(facade)
        self.viewer = RasterViewerView(facade)

        self.account = AccountView(facade)
        account_page = QFrame(objectName="HomeContent")
        account_page.setStyleSheet(f"#HomeContent {{ background: {PAGE_BACKGROUND}; }}")
        centre = QVBoxLayout(account_page)
        centre.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.account)
        row.addStretch(1)
        centre.addLayout(row)
        centre.addStretch(1)

        self.pages = QStackedWidget(objectName="HomePages")
        self.pages.setStyleSheet(f"#HomePages, #DashboardPage {{ background: {PAGE_BACKGROUND}; }}")
        self.dashboard.setObjectName("DashboardPage")
        self.pages.addWidget(self.dashboard)
        self.pages.addWidget(self.query_input)
        self.pages.addWidget(self.downloads)
        self.pages.addWidget(account_page)
        self.pages.addWidget(self.viewer)
        self._account_page = account_page

        # ---- terminal (gkonsol) under the pages
        store = GkonsolStore()
        self.terminal = GkonsolPanel()
        self.terminal_area = TerminalArea(self.pages, self.terminal, store)
        form_view = getattr(self.query_input, "form_view", None)
        form = WidgetForm(form_view) if form_view is not None else MemoryForm(facade)
        self.terminal.start(facade, TerminalApp(self), form, self.terminal_area, History(store))

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.side_bar)
        layout.addWidget(self.terminal_area, 1)
        self.setCentralWidget(root)

        self.sign_out_action.triggered.connect(self.sign_out)
        self.account.session_expired.connect(
            lambda: self.signed_out.emit("Your session has expired. Please sign in again.")
        )
        self.manage_users.clicked.connect(self.open_user_admin)
        self.back_button.clicked.connect(self.show_dashboard)
        self.profile.clicked.connect(self.show_account_menu)
        self.view_account_action.triggered.connect(self.show_account)
        self.signup_details_action.triggered.connect(self.show_signup_details)
        self.dashboard.open_query_input.connect(self.show_query_input)
        self.dashboard.open_downloads.connect(self.show_downloads)
        self.query_input_button.clicked.connect(self.show_query_input)
        self.downloads_button.clicked.connect(self.show_downloads)
        self.terminal_button.clicked.connect(self.toggle_terminal)
        self.terminal_area.visibility_changed.connect(self._terminal_shown)
        app = QApplication.instance()
        if app is not None:  # a command still running when the app quits is stopped first
            app.aboutToQuit.connect(self.terminal.shutdown)
        self.query_input.download_requested.connect(self.start_download)
        self.downloads.view_requested.connect(self.show_viewer)
        self._connect_menu_bar()
        self._admin_dialog: UserAdminDialog | None = None
        self._was_maximized = False  # before going full screen
        self.set_user(user)
        self.show_dashboard()

    # ------------------------------------------------------------- navigation
    def show_dashboard(self) -> None:
        self._show_page(self.dashboard)

    def show_query_input(self) -> None:
        self._show_page(self.query_input)

    def show_downloads(self) -> None:
        self._show_page(self.downloads)

    def start_download(self, form) -> None:
        """Send a kept request to GEE and show its progress on the Downloads page."""
        self.downloads.start(form)
        self.show_downloads()

    def show_account(self) -> None:
        self._show_page(self._account_page)

    def show_viewer(self, path: str) -> None:
        """Show the GeoTIFF at ``path`` on the Viewer page."""
        self.viewer.open(path)
        self._show_page(self.viewer)

    def sign_out(self) -> None:
        self.signed_out.emit("You have been signed out.")

    def exit_app(self) -> None:
        QApplication.quit()  # the active download is paused first (see app.py)

    def set_full_screen(self, on: bool) -> None:
        if on:
            self._was_maximized = self.isMaximized()
            self.showFullScreen()
        elif self._was_maximized:
            self.showMaximized()
        else:
            self.showNormal()
        self.menu_bar.full_screen.setChecked(on)

    def change_theme(self, name: str) -> None:
        """Save the theme and restart, as it is applied when the app starts."""
        answer = QMessageBox.question(
            self, "Change theme",
            f"GEE-Assist restarts to use the {appearance.THEMES[name]} theme. A running download "
            "is paused and can be resumed afterwards.\n\nRestart now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.menu_bar.show_current_theme()
            return
        appearance.save_theme(name)
        restart_app()

    def show_about(self) -> None:
        QMessageBox.about(
            self, "About GEE-Assist",
            "<h3>GEE-Assist</h3>"
            "<p>Describe a request in plain language or fill the parameter form, then download "
            "the imagery from Google Earth Engine in chunks, merged into one GeoTIFF.</p>",
        )

    def current_page(self) -> QWidget:
        return self.pages.currentWidget()

    def _show_page(self, page: QWidget) -> None:
        self.pages.setCurrentWidget(page)
        self.side_bar.show_back(page is not self.dashboard)  # nowhere to go back to on the dashboard
        self.query_input_button.setVisible(page is not self.query_input)
        self.downloads_button.setVisible(page is not self.downloads)
        self.terminal.refresh_prompt()  # the prompt shows the page: ~/downloads

    # ------------------------------------------------------------- terminal
    def toggle_terminal(self) -> None:
        self.terminal_area.toggle_terminal()

    def set_terminal_visible(self, shown: bool) -> None:
        if shown:
            self.terminal_area.show_terminal()
        else:
            self.terminal_area.hide_terminal()

    def _terminal_shown(self, shown: bool) -> None:
        self.terminal_button.setChecked(shown)
        self.menu_bar.toggle_terminal.setChecked(shown)
        self.menu_bar.show_terminal.setChecked(shown)

    def run_in_terminal(self, line: str) -> None:
        """Open the terminal and run ``line`` in it, as if it were typed (the Terminal menu's commands)."""
        self.terminal_area.show_terminal()
        self.terminal.run_command(line)

    def open_command_reference(self) -> None:
        """docs/GKONSOL.md in the app that opens .md files; the terminal's own help if that fails."""
        opened = REFERENCE_FILE.is_file() and QDesktopServices.openUrl(QUrl.fromLocalFile(str(REFERENCE_FILE)))
        if not opened:
            self.run_in_terminal("help")

    def _update_terminal_menu(self) -> None:
        """Before the Terminal menu opens: tick Maximise if it is, and offer Stop only while a command runs."""
        self.menu_bar.maximize_terminal.setChecked(self.terminal_area.is_terminal_maximized())
        self.menu_bar.stop_command.setEnabled(self.terminal.shell.running is not None)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt API)
        self.terminal.shutdown()  # e.g. an Earth Engine sign-in stops waiting for the browser
        super().closeEvent(event)

    # ------------------------------------------------------------- account
    def show_account_menu(self) -> None:
        """The account menu, opening to the right of the user in the side bar."""
        self.account_menu.popup(self.profile.mapToGlobal(QPoint(self.profile.width() + 6, 0)))

    def show_signup_details(self) -> None:
        SignupDetailsDialog(self._user, self).exec()

    def _connect_menu_bar(self) -> None:
        bar = self.menu_bar
        bar.new_request.triggered.connect(self.show_query_input)
        bar.sign_out.triggered.connect(self.sign_out)
        bar.exit.triggered.connect(self.exit_app)
        bar.view_dashboard.triggered.connect(self.show_dashboard)
        bar.view_query_input.triggered.connect(self.show_query_input)
        bar.view_downloads.triggered.connect(self.show_downloads)
        bar.view_account.triggered.connect(self.show_account)
        bar.toggle_side_bar.setChecked(self.side_bar.is_expanded())
        bar.toggle_side_bar.triggered.connect(self.side_bar.set_expanded)
        bar.toggle_terminal.triggered.connect(self.set_terminal_visible)
        self.side_bar.expanded_changed.connect(bar.toggle_side_bar.setChecked)  # also when the logo is clicked
        bar.terminal_menu.aboutToShow.connect(self._update_terminal_menu)
        bar.show_terminal.triggered.connect(self.set_terminal_visible)
        bar.maximize_terminal.triggered.connect(self.terminal_area.set_terminal_maximized)
        bar.clear_terminal.triggered.connect(self.terminal.shell.clear)
        bar.stop_command.triggered.connect(self.terminal.stop_command)
        bar.terminal_command.connect(self.run_in_terminal)
        bar.command_reference.triggered.connect(self.open_command_reference)
        bar.full_screen.triggered.connect(self.set_full_screen)
        bar.chunk_size.triggered.connect(self.downloads.change_chunk_size)
        bar.manage_users.triggered.connect(self.open_user_admin)
        bar.about.triggered.connect(self.show_about)
        bar.theme_chosen.connect(self.change_theme)

    def open_user_admin(self) -> None:
        if self._admin_dialog is None:
            self._admin_dialog = UserAdminDialog(self._facade, self)
            self._admin_dialog.session_expired.connect(
                lambda: self.signed_out.emit("Your session has expired. Please sign in again.")
            )
        else:
            self._admin_dialog.reload()
        self._admin_dialog.show()
        self._admin_dialog.raise_()
        self._admin_dialog.activateWindow()

    def set_user(self, user: UserDTO) -> None:
        self._user = user
        self.profile.set_user(user)
        self.manage_users.setVisible(user.is_admin)
        self.menu_bar.manage_users.setVisible(user.is_admin)
        self.account.set_user(user)
        self.dashboard.set_user(user)
