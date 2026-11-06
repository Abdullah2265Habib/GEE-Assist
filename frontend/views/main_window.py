from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QDockWidget, QMainWindow

from backend.business.facade import IBusinessFacade
from backend.dto import FormDTO
from frontend import form_theme as theme
from frontend.views.kept_requests_view import KeptRequestsView
from frontend.views.parameter_form_view import ParameterFormView


class MainWindow(QMainWindow):
    """The parameter form and a side panel listing the kept requests, with the
    natural-language assistant ("Chat with Gemini") at the bottom of the panel."""

    download_requested = pyqtSignal(object)  # FormDTO: "Start Download" on a kept request

    def __init__(self, facade: IBusinessFacade):
        super().__init__()
        self._facade = facade
        self.setWindowTitle("GEE-Assist")
        self.resize(1150, 760)
        self.setStyleSheet(theme.MAIN_WINDOW_STYLESHEET)

        self.form_view = ParameterFormView(facade)
        self.setCentralWidget(self.form_view)

        self.kept_view = KeptRequestsView(assistant=self.form_view.assistant)
        dock = QDockWidget("Kept Requests")
        dock.setWidget(self.kept_view)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        self.statusBar().setSizeGripEnabled(False)
        self.form_view.request_kept.connect(self._on_request_kept)
        self.kept_view.download_requested.connect(self.download_requested)
        self.statusBar().showMessage("Ready  ·  Press Ctrl+K or Chat with Gemini to describe a request in plain language")

    def _on_request_kept(self, form: FormDTO) -> None:
        self.kept_view.set_requests(self._facade.get_kept_requests())
        self.statusBar().showMessage("Form parameters kept. Press Start Download to fetch the data.", 8000)
