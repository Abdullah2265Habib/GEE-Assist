"""Admin-only user management: list users page by page, change roles, enable / disable accounts."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.auth_exceptions import AuthError, SessionExpiredError
from backend.business.facade import IBusinessFacade
from backend.dto.user_dto import UserDTO, UserPageDTO
from frontend import theme
from frontend.views.account_view import Avatar, format_date
from frontend.widgets.form_widgets import Banner, BusyButton
from frontend.workers.task_worker import run_task

PAGE_SIZE = 25
_COLUMNS = ("Name", "Username", "Email", "Role", "Status", "Email verified", "Sign-in", "Created")

_TABLE_STYLE = f"""
QTableWidget {{
    background: {theme.WHITE}; border: 1px solid {theme.BORDER}; border-radius: 10px;
    gridline-color: transparent; selection-background-color: {theme.MINT}; selection-color: {theme.INK};
    alternate-background-color: {theme.FOAM};
}}
QTableWidget::item {{ padding: 6px 10px; border-bottom: 1px solid {theme.TABLE_LINE}; }}
QHeaderView::section {{
    background: {theme.WHITE}; color: {theme.MUTED}; border: none; border-bottom: 1px solid {theme.BORDER};
    padding: 8px 10px; font-weight: 600; font-size: 9pt;
}}
QComboBox {{
    background: {theme.FIELD_BG}; border: 1px solid {theme.BORDER_STRONG}; border-radius: 8px; padding: 7px 10px;
}}
QComboBox:focus {{ border-color: {theme.LEAF}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{ background: {theme.WHITE}; selection-background-color: {theme.MINT}; }}
"""


class UserDetailsPanel(QFrame):
    """Right-hand panel: the selected user plus the role / status actions."""

    changed = pyqtSignal(object)  # updated UserDTO
    session_expired = pyqtSignal()

    def __init__(self, facade: IBusinessFacade, parent: QWidget | None = None):
        super().__init__(parent)
        self._facade = facade
        self._user: UserDTO | None = None
        self.setObjectName("AuthCard")
        self.setFixedWidth(330)

        self.avatar = Avatar(56)
        self.name = QLabel("Select a user")
        self.name.setWordWrap(True)
        self.name.setStyleSheet(f"font-family: '{theme.SERIF}'; font-size: 15pt; color: {theme.INK};")
        self.meta = QLabel("", objectName="Muted")
        self.meta.setWordWrap(True)
        self.meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.banner = Banner()

        self.role = QComboBox()
        self.role.addItem("User", "user")
        self.role.addItem("Administrator", "admin")
        self.apply_role = BusyButton("Save role", "Saving…", object_name="SecondaryButton")
        self.toggle_status = BusyButton("Disable account", "Saving…", object_name="SecondaryButton")
        self.self_note = QLabel("This is your own account. Another admin must change it.", objectName="FieldHint")
        self.self_note.setWordWrap(True)

        role_label = QLabel("Role", objectName="FieldLabel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(self.avatar)
        layout.addWidget(self.name)
        layout.addWidget(self.meta)
        layout.addWidget(self.banner)
        layout.addSpacing(6)
        layout.addWidget(role_label)
        layout.addWidget(self.role)
        layout.addWidget(self.apply_role)
        layout.addSpacing(6)
        layout.addWidget(self.toggle_status)
        layout.addWidget(self.self_note)
        layout.addStretch(1)

        self.apply_role.clicked.connect(self._save_role)
        self.toggle_status.clicked.connect(self._toggle_status)
        self.show_user(None)

    def show_user(self, user: UserDTO | None) -> None:
        self._user = user
        self.banner.clear()
        has_user = user is not None
        current = self._facade.get_current_user()
        is_self = has_user and current is not None and current.id == user.id
        for widget in (self.avatar, self.role, self.apply_role, self.toggle_status):
            widget.setVisible(has_user)
        self.self_note.setVisible(bool(is_self))
        if not has_user:
            self.name.setText("Select a user")
            self.meta.setText("Choose someone in the list to see their details and manage their access.")
            return
        self.avatar.set_user(user)
        self.name.setText(user.full_name)
        lines = [
            f"@{user.username}",
            user.email or "No email",
            user.phone_number or "No phone number",
            f"Last sign-in: {format_date(user.last_login_at)}",
        ]
        self.meta.setText("\n".join(lines))
        self.role.setCurrentIndex(1 if user.is_admin else 0)
        self.toggle_status.set_idle_text("Disable account" if user.is_active else "Enable account")
        for widget in (self.role, self.apply_role, self.toggle_status):
            widget.setEnabled(not is_self)

    def load(self, user_id: str) -> None:
        """Fetch fresh details (GET /admin/users/{id})."""
        run_task(self, self._facade.get_user, user_id, on_success=self.show_user, on_error=self._on_error)

    def _save_role(self) -> None:
        if self._user is None:
            return
        role = self.role.currentData()
        if role == self._user.role:
            self.banner.show_info("The role is unchanged.")
            return
        self.apply_role.set_busy(True)
        run_task(self, self._facade.set_user_role, self._user.id, role,
                 on_success=lambda u: self._on_changed(u, self.apply_role, "Role updated."),
                 on_error=lambda e: self._on_error(e, self.apply_role))

    def _toggle_status(self) -> None:
        if self._user is None:
            return
        self.toggle_status.set_busy(True)
        active = not self._user.is_active
        run_task(self, self._facade.set_user_active, self._user.id, active,
                 on_success=lambda u: self._on_changed(
                     u, self.toggle_status, "Account enabled." if active else "Account disabled."),
                 on_error=lambda e: self._on_error(e, self.toggle_status))

    def _on_changed(self, user: UserDTO, button: BusyButton, message: str) -> None:
        button.set_busy(False)
        self.show_user(user)
        self.banner.show_success(message)
        self.changed.emit(user)

    def _on_error(self, exc: Exception, button: BusyButton | None = None) -> None:
        if button is not None:
            button.set_busy(False)
        if isinstance(exc, SessionExpiredError):
            self.session_expired.emit()
            return
        self.banner.show_error(str(exc) if isinstance(exc, AuthError) else "Something went wrong.")


class UserAdminDialog(QDialog):
    session_expired = pyqtSignal()

    def __init__(self, facade: IBusinessFacade, parent: QWidget | None = None):
        super().__init__(parent)
        self._facade = facade
        self._page: UserPageDTO | None = None
        self._skip = 0
        self.setWindowTitle("GEE-Assist – User management")
        self.setMinimumSize(1180, 680)
        self.setStyleSheet(f"QDialog {{ background: {theme.WHITE}; }}" + _TABLE_STYLE)

        title = QLabel("User management", objectName="Title")
        self.count = QLabel("", objectName="Subtitle")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter this page by name, username or email")
        self.search.setFixedWidth(340)
        self.refresh = BusyButton("Refresh", "Loading…", object_name="SecondaryButton")
        self.refresh.setFixedWidth(120)
        head = QHBoxLayout()
        head_text = QVBoxLayout()
        head_text.setSpacing(2)
        head_text.addWidget(title)
        head_text.addWidget(self.count)
        head.addLayout(head_text)
        head.addStretch(1)
        head.addWidget(self.search)
        head.addWidget(self.refresh)

        self.banner = Banner()

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(40)
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # name and email share the spare width
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)

        self.prev_button = QPushButton("‹ Previous", objectName="SecondaryButton")
        self.next_button = QPushButton("Next ›", objectName="SecondaryButton")
        self.page_label = QLabel("", objectName="Muted")
        pager = QHBoxLayout()
        pager.addStretch(1)
        pager.addWidget(self.prev_button)
        pager.addWidget(self.page_label)
        pager.addWidget(self.next_button)
        pager.addStretch(1)

        left = QVBoxLayout()
        left.addWidget(self.table, 1)
        left.addLayout(pager)

        self.details = UserDetailsPanel(facade)
        body = QHBoxLayout()
        body.setSpacing(20)
        body.addLayout(left, 1)
        body.addWidget(self.details)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(16)
        layout.addLayout(head)
        layout.addWidget(self.banner)
        layout.addLayout(body, 1)

        self.refresh.clicked.connect(self.reload)
        self.search.textChanged.connect(self._apply_filter)
        self.prev_button.clicked.connect(lambda: self._go(self._skip - PAGE_SIZE))
        self.next_button.clicked.connect(lambda: self._go(self._skip + PAGE_SIZE))
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.details.changed.connect(self._on_user_changed)
        self.details.session_expired.connect(self._expired)

        self.reload()

    # ------------------------------------------------------------------ loading
    def reload(self) -> None:
        self._go(self._skip)

    def _go(self, skip: int) -> None:
        self._skip = max(0, skip)
        self.banner.clear()
        self.refresh.set_busy(True)
        run_task(self, self._facade.list_users, self._skip, PAGE_SIZE, on_success=self._on_page, on_error=self._on_error)

    def _on_page(self, page: UserPageDTO) -> None:
        self.refresh.set_busy(False)
        self._page = page
        self.count.setText(f"{page.total} registered user{'s' if page.total != 1 else ''}")
        self.page_label.setText(f"Page {page.page} of {page.page_count}")
        self.prev_button.setEnabled(page.skip > 0)
        self.next_button.setEnabled(page.skip + page.limit < page.total)
        self.table.setRowCount(len(page.items))
        for row, user in enumerate(page.items):
            self._fill_row(row, user)
        self._apply_filter(self.search.text())
        self.details.show_user(None)

    def _fill_row(self, row: int, user: UserDTO) -> None:
        values = (
            user.full_name,
            user.username,
            user.email or "—",
            "Administrator" if user.is_admin else "User",
            "Active" if user.is_active else "Disabled",
            "Yes" if user.email_verified else "No",
            "Google" if user.auth_provider == "google" else "Password",
            format_date(user.created_at),
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, user.id)
            if column == 4:
                item.setForeground(QColor(theme.SUCCESS if user.is_active else theme.ERROR))
            if column == 3 and user.is_admin:
                item.setForeground(QColor(theme.OCEAN_DARK))
            self.table.setItem(row, column, item)

    def _on_error(self, exc: Exception) -> None:
        self.refresh.set_busy(False)
        if isinstance(exc, SessionExpiredError):
            self._expired()
            return
        self.banner.show_error(str(exc) if isinstance(exc, AuthError) else "Could not load the users.")

    def _expired(self) -> None:
        self.session_expired.emit()
        self.close()

    # ------------------------------------------------------------------ interaction
    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self.table.rowCount()):
            haystack = " ".join(self.table.item(row, c).text().lower() for c in range(3))
            self.table.setRowHidden(row, bool(needle) and needle not in haystack)

    def _on_selection(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows or self._page is None:
            self.details.show_user(None)
            return
        user = self._page.items[rows[0].row()]
        self.details.show_user(user)
        self.details.load(user.id)

    def _on_user_changed(self, user: UserDTO) -> None:
        if self._page is None:
            return
        for row, existing in enumerate(self._page.items):
            if existing.id == user.id:
                self._page.items[row] = user
                self.table.blockSignals(True)
                self._fill_row(row, user)
                self.table.blockSignals(False)
                break
