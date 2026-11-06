from __future__ import annotations

import json

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QListWidget, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from backend.dto import FormDTO


def _summary(index: int, form: FormDTO) -> str:
    if form.source == "nl":
        text = form.query_text if len(form.query_text) <= 40 else form.query_text[:37] + "..."
        return f"#{index}  [Query]  {text}"
    period = f"{form.start_date} → {form.end_date}"
    purpose = form.analysis_type or "download only"
    return f"#{index}  [Form]  {form.dataset} · {purpose} · {period}"


def can_download(form: FormDTO) -> bool:
    """Accepted form parameters have everything GEE needs; bare text queries do not."""
    return form.source == "form" and bool(form.aoi and form.dataset)


class KeptRequestsView(QWidget):
    """Shows every request kept this session; select one to see its parameters or download it."""

    download_requested = pyqtSignal(object)  # FormDTO

    def __init__(self, assistant: QWidget | None = None, parent=None):
        super().__init__(parent)
        self._requests: list[FormDTO] = []

        self._list = QListWidget()
        self.download_button = QPushButton("Start Download", objectName="PrimaryButton")
        self.download_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download_button.setEnabled(False)
        self._details = QPlainTextEdit()
        self._details.setReadOnly(True)
        self._details.setPlaceholderText("Select a request to see its parameters.")

        layout = QVBoxLayout(self)
        layout.addWidget(self._list, 1)
        layout.addWidget(self.download_button)
        layout.addWidget(QLabel("Parameters"))
        layout.addWidget(self._details, 2)
        if assistant is not None:
            # Sits under the parameters; opening it shrinks the parameters view.
            layout.addSpacing(4)
            layout.addWidget(assistant)
        self._details.setMinimumHeight(90)
        self.setMinimumWidth(320)

        self._list.currentRowChanged.connect(self._show_details)
        self.download_button.clicked.connect(self._request_download)

    def set_requests(self, requests: list[FormDTO]) -> None:
        self._requests = requests
        self._list.clear()
        for i, form in enumerate(requests, start=1):
            self._list.addItem(_summary(i, form))
        if requests:
            self._list.setCurrentRow(len(requests) - 1)

    def _show_details(self, row: int) -> None:
        if 0 <= row < len(self._requests):
            data = self._requests[row].to_dict()
            if data.get("aoi"):
                data["aoi"] = json.loads(data["aoi"])
            self._details.setPlainText(json.dumps(data, indent=2))
        else:
            self._details.clear()
        form = self.selected_request()
        downloadable = form is not None and can_download(form)
        self.download_button.setEnabled(downloadable)
        self.download_button.setToolTip(
            "Fetch this dataset from Google Earth Engine" if downloadable
            else "Fill the form (or let Gemini fill it) and press Submit Parameters first"
        )

    def selected_request(self) -> FormDTO | None:
        row = self._list.currentRow()
        return self._requests[row] if 0 <= row < len(self._requests) else None

    def _request_download(self) -> None:
        form = self.selected_request()
        if form is not None and can_download(form):
            self.download_requested.emit(form)
