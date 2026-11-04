from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDockWidget, QMainWindow, QTabWidget

from backend.business.facade import IBusinessFacade
from backend.dto import FormDTO
from frontend.views.kept_requests_view import KeptRequestsView
from frontend.views.parameter_form_view import ParameterFormView
from frontend.views.query_view import QueryView


class MainWindow(QMainWindow):
    """Two input paths (tabs) and a side panel listing the kept requests."""

    def __init__(self, facade: IBusinessFacade):
        super().__init__()
        self._facade = facade
        self.setWindowTitle("GEE-Assist")
        self.resize(1150, 760)

        self.form_view = ParameterFormView(facade)
        self.query_view = QueryView(facade)

        tabs = QTabWidget()
        tabs.addTab(self.form_view, "Parameter Form")
        tabs.addTab(self.query_view, "Natural Language Query")
        self.setCentralWidget(tabs)

        self.kept_view = KeptRequestsView()
        dock = QDockWidget("Kept Requests")
        dock.setWidget(self.kept_view)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        self.form_view.request_kept.connect(self._on_request_kept)
        self.query_view.request_kept.connect(self._on_request_kept)

        self.statusBar().showMessage("Ready")

    def _on_request_kept(self, form: FormDTO) -> None:
        self.kept_view.set_requests(self._facade.get_kept_requests())
        label = "Form parameters" if form.source == "form" else "Natural-language query"
        self.statusBar().showMessage(f"{label} kept.", 5000)
