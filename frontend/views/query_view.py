from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from backend.business.facade import IBusinessFacade


class QueryView(QWidget):
    """UC-02 Enter Natural Language Query (built on branch query-input-nl)."""

    request_kept = pyqtSignal(object)  # FormDTO

    def __init__(self, facade: IBusinessFacade, parent=None):
        super().__init__(parent)
        self._facade = facade
        layout = QVBoxLayout(self)
        label = QLabel("Natural-language query: implemented on branch query-input-nl.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
