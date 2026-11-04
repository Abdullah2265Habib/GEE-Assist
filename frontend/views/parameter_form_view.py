"""UC-03 Fill Parameter Form + UC-04 Import GeoJSON."""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.business.facade import IBusinessFacade
from backend.config import ANALYSIS_CATEGORIES, COMPOSITE_METHODS, DATASETS, get_dataset
from backend.dto import FormDTO, ValidationDTO
from backend.exceptions import GeeAssistError

ERROR_STYLE = "color: #c0392b;"
SUCCESS_STYLE = "color: #1e8449; font-weight: bold;"


def _bbox_polygon(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> str:
    ring = [[min_lon, min_lat], [max_lon, min_lat], [max_lon, max_lat], [min_lon, max_lat], [min_lon, min_lat]]
    return json.dumps({"type": "Polygon", "coordinates": [ring]})


def _bbox_of(geometry: dict) -> list[float]:
    coords = geometry["coordinates"]
    polygons = [coords] if geometry["type"] == "Polygon" else coords
    points = [p for poly in polygons for ring in poly for p in ring]
    lons, lats = [p[0] for p in points], [p[1] for p in points]
    return [min(lons), min(lats), max(lons), max(lats)]


def _checked_items(widget: QListWidget) -> list[str]:
    return [
        widget.item(i).text()
        for i in range(widget.count())
        if widget.item(i).checkState() == Qt.CheckState.Checked
    ]


def _fill_checklist(widget: QListWidget, values, checked=()) -> None:
    widget.clear()
    for value in values:
        item = QListWidgetItem(value)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if value in checked else Qt.CheckState.Unchecked)
        widget.addItem(item)


class ParameterFormView(QWidget):
    """Collects every parameter GEE needs to fetch data, validates and keeps it."""

    request_kept = pyqtSignal(object)  # FormDTO

    def __init__(self, facade: IBusinessFacade, parent=None):
        super().__init__(parent)
        self._facade = facade
        self._imported_aoi: str = ""
        self._imported_name: str = ""
        self._error_labels: dict[str, QLabel] = {}

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.addWidget(self._build_dataset_group())
        content_layout.addWidget(self._build_aoi_group())
        content_layout.addWidget(self._build_time_group())
        content_layout.addWidget(self._build_analysis_group())
        content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.reset_button = QPushButton("Reset")
        self.submit_button = QPushButton("Submit Parameters")
        self.submit_button.setDefault(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.status_label, 1)
        buttons.addWidget(self.reset_button)
        buttons.addWidget(self.submit_button)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addLayout(buttons)

        self.dataset_combo.currentIndexChanged.connect(self._on_dataset_changed)
        self.analysis_combo.currentIndexChanged.connect(self._on_analysis_changed)
        self.import_button.clicked.connect(self._on_import_geojson)
        self.reset_button.clicked.connect(self.reset)
        self.submit_button.clicked.connect(self._on_submit)

        self.reset()

    # ------------------------------------------------------------------ build
    def _error_label(self, key: str) -> QLabel:
        label = QLabel()
        label.setStyleSheet(ERROR_STYLE)
        label.setWordWrap(True)
        label.hide()
        self._error_labels[key] = label
        return label

    def _build_dataset_group(self) -> QGroupBox:
        group = QGroupBox("1. Dataset")
        form = QFormLayout(group)

        self.dataset_combo = QComboBox()
        for key, info in DATASETS.items():
            self.dataset_combo.addItem(info.name, key)
        self.collection_label = QLabel()
        self.collection_label.setStyleSheet("color: gray;")
        self.collection_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.bands_list = QListWidget()
        self.bands_list.setMaximumHeight(130)

        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(1, 100_000)
        self.scale_spin.setSuffix(" m / pixel")

        self.cloud_spin = QSpinBox()
        self.cloud_spin.setRange(0, 100)
        self.cloud_spin.setSuffix(" %")
        self.cloud_spin.setToolTip("Scenes with more cloud cover than this are excluded.")

        self.composite_combo = QComboBox()
        self.composite_combo.addItems(COMPOSITE_METHODS)
        self.composite_combo.setToolTip("How multiple images in the time range are combined into one.")

        form.addRow("Dataset:", self.dataset_combo)
        form.addRow("", self.collection_label)
        form.addRow("", self._error_label("dataset"))
        form.addRow("Bands:", self.bands_list)
        form.addRow("", self._error_label("bands"))
        form.addRow("Scale:", self.scale_spin)
        form.addRow("", self._error_label("scale"))
        form.addRow("Max cloud cover:", self.cloud_spin)
        form.addRow("", self._error_label("max_cloud_cover"))
        form.addRow("Composite:", self.composite_combo)
        form.addRow("", self._error_label("composite"))
        return group

    def _build_aoi_group(self) -> QGroupBox:
        group = QGroupBox("2. Area of Interest")
        layout = QVBoxLayout(group)

        self.aoi_file_radio = QRadioButton("Import GeoJSON file")
        self.aoi_bbox_radio = QRadioButton("Enter bounding box")
        self._aoi_mode = QButtonGroup(self)
        self._aoi_mode.addButton(self.aoi_file_radio, 0)
        self._aoi_mode.addButton(self.aoi_bbox_radio, 1)
        modes = QHBoxLayout()
        modes.addWidget(self.aoi_file_radio)
        modes.addWidget(self.aoi_bbox_radio)
        modes.addStretch(1)

        # page 0: GeoJSON import
        file_page = QWidget()
        file_layout = QVBoxLayout(file_page)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.import_button = QPushButton("Import GeoJSON…")
        self.aoi_file_label = QLabel("No file imported.")
        self.aoi_file_label.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(self.import_button)
        row.addWidget(self.aoi_file_label, 1)
        file_layout.addLayout(row)

        # page 1: bounding box
        bbox_page = QWidget()
        grid = QGridLayout(bbox_page)
        grid.setContentsMargins(0, 0, 0, 0)

        def coord_spin(limit: float) -> QDoubleSpinBox:
            spin = QDoubleSpinBox()
            spin.setRange(-limit, limit)
            spin.setDecimals(6)
            spin.setSingleStep(0.01)
            return spin

        self.min_lon_spin, self.max_lon_spin = coord_spin(180), coord_spin(180)
        self.min_lat_spin, self.max_lat_spin = coord_spin(90), coord_spin(90)
        grid.addWidget(QLabel("Min longitude:"), 0, 0)
        grid.addWidget(self.min_lon_spin, 0, 1)
        grid.addWidget(QLabel("Max longitude:"), 0, 2)
        grid.addWidget(self.max_lon_spin, 0, 3)
        grid.addWidget(QLabel("Min latitude:"), 1, 0)
        grid.addWidget(self.min_lat_spin, 1, 1)
        grid.addWidget(QLabel("Max latitude:"), 1, 2)
        grid.addWidget(self.max_lat_spin, 1, 3)

        self.aoi_stack = QStackedWidget()
        self.aoi_stack.addWidget(file_page)
        self.aoi_stack.addWidget(bbox_page)
        self._aoi_mode.idClicked.connect(self.aoi_stack.setCurrentIndex)

        layout.addLayout(modes)
        layout.addWidget(self.aoi_stack)
        layout.addWidget(self._error_label("aoi"))
        return group

    def _build_time_group(self) -> QGroupBox:
        group = QGroupBox("3. Time Range")
        form = QFormLayout(group)

        def date_edit() -> QDateEdit:
            edit = QDateEdit()
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
            edit.setMaximumDate(QDate.currentDate())
            return edit

        self.start_date_edit = date_edit()
        self.end_date_edit = date_edit()
        form.addRow("Start date:", self.start_date_edit)
        form.addRow("End date:", self.end_date_edit)
        form.addRow("", self._error_label("dates"))
        return group

    def _build_analysis_group(self) -> QGroupBox:
        group = QGroupBox("4. Analysis")
        form = QFormLayout(group)
        self.analysis_combo = QComboBox()
        self.processes_list = QListWidget()
        self.processes_list.setMaximumHeight(110)
        form.addRow("Analysis type:", self.analysis_combo)
        form.addRow("", self._error_label("analysis_type"))
        form.addRow("Processes:", self.processes_list)
        form.addRow("", self._error_label("processes"))
        return group

    # ------------------------------------------------------------- behaviour
    def reset(self) -> None:
        self.dataset_combo.setCurrentIndex(0)
        self._on_dataset_changed()
        self.composite_combo.setCurrentText("median")
        self.aoi_file_radio.setChecked(True)
        self.aoi_stack.setCurrentIndex(0)
        self._imported_aoi = ""
        self._imported_name = ""
        self.aoi_file_label.setText("No file imported.")
        for spin in (self.min_lon_spin, self.min_lat_spin, self.max_lon_spin, self.max_lat_spin):
            spin.setValue(0.0)
        today = QDate.currentDate()
        self.end_date_edit.setDate(today)
        self.start_date_edit.setDate(today.addMonths(-3))
        self._show_validation(ValidationDTO())
        self.status_label.clear()

    def _on_dataset_changed(self) -> None:
        info = get_dataset(self.dataset_combo.currentData())
        if info is None:
            return
        self.collection_label.setText(info.collection_id)
        _fill_checklist(self.bands_list, info.bands, checked=info.default_bands)
        self.scale_spin.setValue(info.default_scale)

        self.cloud_spin.setEnabled(info.supports_cloud_filter)
        self.cloud_spin.setValue(20 if info.supports_cloud_filter else 0)

        min_date = QDate(info.min_date.year, info.min_date.month, info.min_date.day)
        self.start_date_edit.setMinimumDate(min_date)
        self.end_date_edit.setMinimumDate(min_date)

        previous = self.analysis_combo.currentText()
        self.analysis_combo.blockSignals(True)
        self.analysis_combo.clear()
        self.analysis_combo.addItems(info.supported_analyses.keys())
        if previous in info.supported_analyses:
            self.analysis_combo.setCurrentText(previous)
        self.analysis_combo.blockSignals(False)
        self._on_analysis_changed()

    def _on_analysis_changed(self) -> None:
        processes = ANALYSIS_CATEGORIES.get(self.analysis_combo.currentText(), ())
        _fill_checklist(self.processes_list, processes)

    def _on_import_geojson(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import GeoJSON", "", "GeoJSON files (*.geojson *.json);;All files (*)"
        )
        if not path:  # 6c: user cancelled
            return
        try:
            aoi = self._facade.import_aoi(path)
        except GeeAssistError as exc:  # 6a / 6b
            self._imported_aoi = ""
            self.aoi_file_label.setText("No file imported.")
            self._set_field_error("aoi", str(exc))
            return

        self._imported_aoi = aoi
        self._imported_name = Path(path).name
        geometry = json.loads(aoi)
        min_lon, min_lat, max_lon, max_lat = _bbox_of(geometry)
        self.aoi_file_label.setText(
            f"<b>{self._imported_name}</b> · {geometry['type']}<br>"
            f"Extent: lon {min_lon:.4f} → {max_lon:.4f}, lat {min_lat:.4f} → {max_lat:.4f}"
        )
        self._set_field_error("aoi", "")

    def collect_form(self) -> FormDTO:
        """Build a FormDTO from the current widget values."""
        if self.aoi_file_radio.isChecked():
            aoi, aoi_name = self._imported_aoi, self._imported_name
        else:
            aoi = _bbox_polygon(
                self.min_lon_spin.value(), self.min_lat_spin.value(),
                self.max_lon_spin.value(), self.max_lat_spin.value(),
            )
            aoi_name = "Bounding box"

        return FormDTO(
            dataset=self.dataset_combo.currentData(),
            bands=_checked_items(self.bands_list),
            scale=self.scale_spin.value(),
            max_cloud_cover=self.cloud_spin.value() if self.cloud_spin.isEnabled() else None,
            composite=self.composite_combo.currentText(),
            aoi=aoi,
            aoi_name=aoi_name,
            start_date=self.start_date_edit.date().toPyDate(),
            end_date=self.end_date_edit.date().toPyDate(),
            analysis_type=self.analysis_combo.currentText(),
            processes=_checked_items(self.processes_list),
            source="form",
        )

    def _on_submit(self) -> None:
        form = self.collect_form()
        try:
            result = self._facade.submit_form(form)
        except GeeAssistError as exc:
            self.status_label.setStyleSheet(ERROR_STYLE)
            self.status_label.setText(str(exc))
            return

        self._show_validation(result)
        if result.is_valid:
            self.request_kept.emit(form)

    def _show_validation(self, result: ValidationDTO) -> None:
        for key in self._error_labels:
            self._set_field_error(key, result.errors.get(key, ""))
        self.status_label.setStyleSheet(SUCCESS_STYLE if result.is_valid else ERROR_STYLE)
        self.status_label.setText(result.message)

    def _set_field_error(self, key: str, message: str) -> None:
        label = self._error_labels[key]
        label.setText(message)
        label.setVisible(bool(message))
