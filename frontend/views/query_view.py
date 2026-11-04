"""UC-02 Enter Natural Language Query."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from backend.business.facade import IBusinessFacade
from backend.config.limits import MAX_QUERY_LENGTH
from backend.exceptions import GeeAssistError

ERROR_STYLE = "color: #c0392b;"
SUCCESS_STYLE = "color: #1e8449; font-weight: bold;"

EXAMPLE_QUERIES = (
    "Show NDVI for Faisalabad from June to August 2024 using Sentinel-2",
    "Map water bodies around Mangla Dam in 2023 and estimate water area",
    "Land surface temperature trend for Lahore over the last 3 summers",
    "Land cover change in Islamabad between 2018 and 2024",
)


class QueryView(QWidget):
    """Lets the user describe the data they need in plain language and keeps it."""

    request_kept = pyqtSignal(object)  # FormDTO

    def __init__(self, facade: IBusinessFacade, parent=None):
        super().__init__(parent)
        self._facade = facade

        intro = QLabel(
            "<b>Describe the data or analysis you need.</b><br>"
            "Mention the place, the time period and what you want to analyse "
            "(e.g. vegetation, water, temperature, land cover)."
        )
        intro.setWordWrap(True)

        self.examples_combo = QComboBox()
        self.examples_combo.addItem("Insert an example…")
        self.examples_combo.addItems(EXAMPLE_QUERIES)

        self.query_edit = QPlainTextEdit()
        self.query_edit.setPlaceholderText(
            "e.g. Show NDVI for Faisalabad from June to August 2024 using Sentinel-2"
        )

        self.counter_label = QLabel()
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        self.clear_button = QPushButton("Clear")
        self.submit_button = QPushButton("Submit Query")
        self.submit_button.setDefault(True)
        self.submit_button.setToolTip("Ctrl+Enter")

        top = QHBoxLayout()
        top.addWidget(intro, 1)
        top.addWidget(self.examples_combo)

        bottom = QHBoxLayout()
        bottom.addWidget(self.counter_label)
        bottom.addWidget(self.status_label, 1)
        bottom.addWidget(self.clear_button)
        bottom.addWidget(self.submit_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.query_edit, 1)
        layout.addLayout(bottom)

        self.examples_combo.activated.connect(self._on_example_chosen)
        self.query_edit.textChanged.connect(self._update_counter)
        self.clear_button.clicked.connect(self.clear)
        self.submit_button.clicked.connect(self._on_submit)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._on_submit)

        self._update_counter()

    # ------------------------------------------------------------- behaviour
    def clear(self) -> None:
        self.query_edit.clear()
        self.status_label.clear()
        self.query_edit.setFocus()

    def _on_example_chosen(self, index: int) -> None:
        if index > 0:
            self.query_edit.setPlainText(self.examples_combo.itemText(index))
        self.examples_combo.setCurrentIndex(0)

    def _update_counter(self) -> None:
        length = len(self.query_edit.toPlainText())
        self.counter_label.setText(f"{length} / {MAX_QUERY_LENGTH}")
        self.counter_label.setStyleSheet(ERROR_STYLE if length > MAX_QUERY_LENGTH else "color: gray;")

    def _on_submit(self) -> None:
        try:
            form = self._facade.submit_query(self.query_edit.toPlainText())
        except GeeAssistError as exc:  # 5a: empty query, or too long
            self.status_label.setStyleSheet(ERROR_STYLE)
            self.status_label.setText(str(exc))
            return

        self.status_label.setStyleSheet(SUCCESS_STYLE)
        self.status_label.setText("Query kept. It will be interpreted into parameters in the next stage.")
        self.request_kept.emit(form)
