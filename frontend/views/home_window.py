"""Window shown after signing in: header with the user and "Sign out", account card in the middle.

The query / analysis workspace (MainWindow on the query-input branches) takes this place once
the branches are merged.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from backend.business.facade import IBusinessFacade
from backend.dto.user_dto import UserDTO
from frontend import theme
from frontend.views.account_view import AccountView, Avatar
from frontend.views.auth.hero_panel import round_logo


class HomeWindow(QMainWindow):
    signed_out = pyqtSignal(str)  # message for the sign-in screen

    def __init__(self, facade: IBusinessFacade, user: UserDTO, parent: QWidget | None = None):
        super().__init__(parent)
        self._facade = facade
        self.setWindowTitle("GEE-Assist")
        self.setMinimumSize(1000, 680)

        # ---- header
        logo = QLabel()
        logo.setPixmap(round_logo(36, self.devicePixelRatioF()))
        name = QLabel("GEE-Assist")
        name.setStyleSheet(f"font-family: '{theme.SERIF}'; font-size: 15pt; color: {theme.INK};")
        self.user_avatar = Avatar(34)
        self.user_name = QLabel()
        self.user_name.setStyleSheet(f"color: {theme.INK}; font-weight: 600;")
        self.user_role = QLabel(objectName="Muted")
        who = QVBoxLayout()
        who.setSpacing(0)
        who.addWidget(self.user_name)
        who.addWidget(self.user_role)
        self.sign_out_button = QPushButton("Sign out", objectName="SecondaryButton")
        self.sign_out_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.header_actions = QHBoxLayout()  # extra buttons (e.g. user management) go here
        self.header_actions.setSpacing(10)

        header = QFrame(objectName="HomeHeader")
        header.setStyleSheet(
            f"#HomeHeader {{ background: {theme.WHITE}; border-bottom: 1px solid {theme.BORDER}; }}"
        )
        bar = QHBoxLayout(header)
        bar.setContentsMargins(28, 12, 28, 12)
        bar.setSpacing(12)
        bar.addWidget(logo)
        bar.addWidget(name)
        bar.addStretch(1)
        bar.addLayout(self.header_actions)
        bar.addSpacing(8)
        bar.addWidget(self.user_avatar)
        bar.addLayout(who)
        bar.addSpacing(8)
        bar.addWidget(self.sign_out_button)

        # ---- content
        self.account = AccountView(facade)
        content = QFrame(objectName="HomeContent")
        content.setStyleSheet(
            "#HomeContent { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            "stop:0 #F3FAF6, stop:0.6 #F2F8FB, stop:1 #ECF4FB); }"
        )
        centre = QVBoxLayout(content)
        centre.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.account)
        row.addStretch(1)
        centre.addLayout(row)
        centre.addStretch(1)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(content, 1)
        self.setCentralWidget(root)

        self.sign_out_button.clicked.connect(lambda: self.signed_out.emit("You have been signed out."))
        self.account.session_expired.connect(
            lambda: self.signed_out.emit("Your session has expired. Please sign in again.")
        )
        self.set_user(user)

    def set_user(self, user: UserDTO) -> None:
        self.user_avatar.set_user(user)
        self.user_name.setText(user.full_name)
        self.user_role.setText("Administrator" if user.is_admin else "User")
        self.account.set_user(user)
