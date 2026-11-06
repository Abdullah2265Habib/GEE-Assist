"""The first window: intro video, then (after it fades out) the page passed in as ``next_view``."""

from __future__ import annotations

from PyQt6.QtWidgets import QMainWindow, QStackedWidget, QWidget

from frontend.assets import STARTING_VIDEO
from frontend.views.splash_view import SplashView
from frontend.widgets.fade import fade_in

NEXT_VIEW_FADE_IN_MS = 700


class StartupWindow(QMainWindow):
    def __init__(self, next_view: QWidget, play_intro: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("GEE-Assist")
        self.setObjectName("StartupWindow")
        self.setStyleSheet("#StartupWindow, #StartupStack { background: #FFFFFF; }")
        self.setMinimumSize(1000, 680)

        self._stack = QStackedWidget(self)
        self._stack.setObjectName("StartupStack")
        self.setCentralWidget(self._stack)

        self._next_view = next_view
        self._splash: SplashView | None = None
        if play_intro:
            self._splash = SplashView(STARTING_VIDEO)
            self._splash.finished.connect(self._show_next_view)
            self._stack.addWidget(self._splash)
        self._stack.addWidget(next_view)

    def start(self) -> None:
        """Show the window maximised (so the video is centred on the user's screen) and play the intro."""
        self.showMaximized()
        if self._splash is not None:
            self._splash.start()
        else:
            self._show_next_view()

    def _show_next_view(self) -> None:
        self._stack.setCurrentWidget(self._next_view)
        fade_in(self._next_view, NEXT_VIEW_FADE_IN_MS)
        if self._splash is not None:
            self._stack.removeWidget(self._splash)
            self._splash.deleteLater()
            self._splash = None
