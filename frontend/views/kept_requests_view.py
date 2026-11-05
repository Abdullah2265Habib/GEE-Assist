from __future__ import annotations

import json

from PyQt6.QtWidgets import QLabel, QListWidget, QPlainTextEdit, QVBoxLayout, QWidget

from backend.dto import FormDTO


def _summary(index: int, form: FormDTO) -> str:
    if form.source == "nl":
        text = form.query_text if len(form.query_text) <= 40 else form.query_text[:37] + "..."
        return f"#{index}  [Query]  {text}"
    period = f"{form.start_date} → {form.end_date}"
    purpose = form.analysis_type or "download only"
    return f"#{index}  [Form]  {form.dataset} · {purpose} · {period}"


class KeptRequestsView(QWidget):
    """Shows every request kept this session; select one to see its parameters."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._requests: list[FormDTO] = []

        self._list = QListWidget()
        self._details = QPlainTextEdit()
        self._details.setReadOnly(True)
        self._details.setPlaceholderText("Select a request to see its parameters.")

        layout = QVBoxLayout(self)
        layout.addWidget(self._list, 1)
        layout.addWidget(QLabel("Parameters"))
        layout.addWidget(self._details, 2)
        self.setMinimumWidth(320)

        self._list.currentRowChanged.connect(self._show_details)

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
