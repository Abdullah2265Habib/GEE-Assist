from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from backend.business.facade import IBusinessFacade


class ParameterFormView(QWidget):
    """UC-03 Fill Parameter Form + UC-04 Import GeoJSON (built on branch query-input-form)."""

    request_kept = pyqtSignal(object)  # FormDTO

    def __init__(self, facade: IBusinessFacade, parent=None):
        super().__init__(parent)
        self._facade = facade
        layout = QVBoxLayout(self)
        label = QLabel("Parameter form: implemented on branch query-input-form.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
