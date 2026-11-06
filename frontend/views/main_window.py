from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDockWidget, QLabel, QMainWindow, QStackedWidget

from backend.business.facade import IBusinessFacade
from backend.dto import FormDTO
from frontend import form_theme as theme
from frontend.views.kept_requests_view import KeptRequestsView
from frontend.views.parameter_form_view import ParameterFormView
from frontend.views.query_view import QueryView
from frontend.widgets.mode_switcher import ModeSwitcher

FORM_MODE, QUERY_MODE = 0, 1


class MainWindow(QMainWindow):
    """Two input paths, switched from a drop-up in the bottom-right corner,
    and a side panel listing the kept requests."""

    def __init__(self, facade: IBusinessFacade):
        super().__init__()
        self._facade = facade
        self.setWindowTitle("GEE-Assist")
        self.resize(1150, 760)
        self.setStyleSheet(theme.MAIN_WINDOW_STYLESHEET)

        self.form_view = ParameterFormView(facade)
        self.query_view = QueryView(facade)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.form_view)   # FORM_MODE
        self.pages.addWidget(self.query_view)  # QUERY_MODE
        self.setCentralWidget(self.pages)

        self.kept_view = KeptRequestsView()
        dock = QDockWidget("Kept Requests")
        dock.setWidget(self.kept_view)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        # Bottom bar: status messages on the left, input-mode drop-up on the right.
        self.mode_switcher = ModeSwitcher()
        self.mode_switcher.add_mode("Parameter Form", "Fill in every parameter yourself.", "Ctrl+1")
        self.mode_switcher.add_mode("Natural Language Query", "Describe the request in plain English.", "Ctrl+2")
        self.mode_switcher.mode_changed.connect(self.pages.setCurrentIndex)
        self.addActions(self.mode_switcher.mode_actions())  # Ctrl+1 / Ctrl+2 anywhere in the window
        self.mode_switcher.setToolTip("Switch input mode (Ctrl+1 / Ctrl+2)")
        mode_caption = QLabel("Input mode:")
        mode_caption.setObjectName("ModeCaption")
        self.statusBar().addPermanentWidget(mode_caption)
        self.statusBar().addPermanentWidget(self.mode_switcher)
        self.statusBar().setSizeGripEnabled(False)

        self.form_view.request_kept.connect(self._on_request_kept)
        self.query_view.request_kept.connect(self._on_request_kept)

        self.statusBar().showMessage("Ready")

    def _on_request_kept(self, form: FormDTO) -> None:
        self.kept_view.set_requests(self._facade.get_kept_requests())
        label = "Form parameters" if form.source == "form" else "Natural-language query"
        self.statusBar().showMessage(f"{label} kept.", 5000)
