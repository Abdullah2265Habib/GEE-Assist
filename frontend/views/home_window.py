"""Window shown after signing in.

A side bar on the left (logo, navigation and the signed-in user) next to
four pages: the dashboard (start page), the query-input workspace, downloads and the
account card. Clicking the logo slides the side bar open or closed; clicking the user
opens the account menu (account options and "Sign out").
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QMouseEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.business.facade import IBusinessFacade
from backend.dto.user_dto import UserDTO
from frontend import theme
from frontend.views.account_view import AccountView, Avatar, SignupDetailsDialog
from frontend.views.auth.hero_panel import round_logo
from frontend.views.dashboard_view import DashboardView
from frontend.views.download_view import DownloadView
from frontend.views.main_window import MainWindow
from frontend.views.user_admin_view import UserAdminDialog
from frontend.widgets.side_bar import LOGO_SIZE, SideBar

MENU_STYLE = f"""
QMenu {{ background: {theme.WHITE}; border: 1px solid {theme.BORDER}; border-radius: 8px; padding: 6px; }}
QMenu::item {{ color: {theme.INK}; padding: 8px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {theme.FOAM}; }}
QMenu::item:disabled {{ color: {theme.SUBTLE}; }}
"""


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


class HomeWindow(QMainWindow):
    signed_out = pyqtSignal(str)  # message for the sign-in screen

    def __init__(self, facade: IBusinessFacade, user: UserDTO, parent: QWidget | None = None):
        super().__init__(parent)
        self._facade = facade
        self._user = user
        self.setWindowTitle("GEE-Assist")
        self.setMinimumSize(1000, 680)

        # ---- side bar
        self.side_bar = SideBar(round_logo(LOGO_SIZE, self.devicePixelRatioF()))
        self.back_button = self.side_bar.back_button
        self.back_button.setToolTip("Back to the dashboard")
        self.dashboard_button = self.side_bar.add_button("Dashboard", "Db")
        self.dashboard_button.setToolTip("Back to the dashboard")
        self.downloads_button = self.side_bar.add_button("Downloads", "D")
        self.manage_users = self.side_bar.add_button("Manage users", "M")
        self.manage_users.setToolTip("Administrators: view accounts, change roles, enable or disable users")
        self.profile = ProfileButton()
        self.side_bar.add_widget(self.profile, footer=True)

        # ---- account menu
        self.account_menu = QMenu(self)
        self.account_menu.setStyleSheet(MENU_STYLE)
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

        self.account = AccountView(facade)
        account_page = QFrame(objectName="HomeContent")
        account_page.setStyleSheet(
            "#HomeContent { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            "stop:0 #F3FAF6, stop:0.6 #F2F8FB, stop:1 #ECF4FB); }"
        )
        centre = QVBoxLayout(account_page)
        centre.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.account)
        row.addStretch(1)
        centre.addLayout(row)
        centre.addStretch(1)

        self.pages = QStackedWidget(objectName="HomePages")
        self.pages.setStyleSheet(
            "#HomePages, #DashboardPage { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            "stop:0 #F3FAF6, stop:0.6 #F2F8FB, stop:1 #ECF4FB); }"
        )
        self.dashboard.setObjectName("DashboardPage")
        self.pages.addWidget(self.dashboard)
        self.pages.addWidget(self.query_input)
        self.pages.addWidget(self.downloads)
        self.pages.addWidget(account_page)
        self._account_page = account_page

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.side_bar)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)

        self.sign_out_action.triggered.connect(lambda: self.signed_out.emit("You have been signed out."))
        self.account.session_expired.connect(
            lambda: self.signed_out.emit("Your session has expired. Please sign in again.")
        )
        self.manage_users.clicked.connect(self._open_user_admin)
        self.dashboard_button.clicked.connect(self.show_dashboard)
        self.back_button.clicked.connect(self.show_dashboard)
        self.profile.clicked.connect(self.show_account_menu)
        self.view_account_action.triggered.connect(self.show_account)
        self.signup_details_action.triggered.connect(self.show_signup_details)
        self.dashboard.open_query_input.connect(self.show_query_input)
        self.dashboard.open_downloads.connect(self.show_downloads)
        self.downloads_button.clicked.connect(self.show_downloads)
        self.query_input.download_requested.connect(self.start_download)
        self._admin_dialog: UserAdminDialog | None = None
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

    def current_page(self) -> QWidget:
        return self.pages.currentWidget()

    def _show_page(self, page: QWidget) -> None:
        self.pages.setCurrentWidget(page)
        self.dashboard_button.setVisible(page is not self.dashboard)
        self.back_button.setVisible(page is not self.dashboard)  # nowhere to go back to on the dashboard
        self.downloads_button.setVisible(page is not self.downloads)

    # ------------------------------------------------------------- account
    def show_account_menu(self) -> None:
        """The account menu, opening to the right of the user in the side bar."""
        self.account_menu.popup(self.profile.mapToGlobal(QPoint(self.profile.width() + 6, 0)))

    def show_signup_details(self) -> None:
        SignupDetailsDialog(self._user, self).exec()

    def _open_user_admin(self) -> None:
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
        self.account.set_user(user)
        self.dashboard.set_user(user)
