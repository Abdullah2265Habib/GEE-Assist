"""UC-03 Fill Parameter Form + UC-04 Import GeoJSON."""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtGui import QFont
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
from backend.config import (
    ANALYSIS_CATEGORIES,
    COMPOSITE_METHODS,
    DatasetInfo,
    datasets_by_category,
    get_dataset,
)
from backend.dto import FormDTO, ValidationDTO
from backend.exceptions import GeeAssistError
from frontend import form_theme as theme
from frontend.aoi_geometry import (
    bbox_of,
    bbox_polygon,
    circle_polygon,
    format_distance,
    polygon_from_geojson,
    vertex_count,
)
from frontend.widgets.aoi_map_widget import AoiMapWidget

ERROR_STYLE = f"color: {theme.ERROR};"
SUCCESS_STYLE = f"color: {theme.SUCCESS}; font-weight: 600;"
HINT_STYLE = f"color: {theme.MUTED}; font-size: 9pt;"

AOI_FILE, AOI_DRAW = 0, 1
NO_SHAPE_TEXT = "No shape drawn yet."


# ---------------------------------------------------------------------- helpers
def _qdate(value) -> QDate:
    return QDate(value.year, value.month, value.day)


def _checked_items(widget: QListWidget) -> list[str]:
    return [
        widget.item(i).text()
        for i in range(widget.count())
        if widget.item(i).flags() & Qt.ItemFlag.ItemIsEnabled
        and widget.item(i).checkState() == Qt.CheckState.Checked
    ]


def _add_check_item(widget: QListWidget, text: str, checked: bool, enabled: bool = True, tooltip: str = "") -> None:
    item = QListWidgetItem(text)
    flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
    if not enabled:
        flags &= ~(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
    item.setFlags(flags)
    item.setCheckState(Qt.CheckState.Checked if checked and enabled else Qt.CheckState.Unchecked)
    if tooltip:
        item.setToolTip(tooltip)
    widget.addItem(item)


def _set_combo_item_enabled(combo: QComboBox, index: int, enabled: bool, tooltip: str = "") -> None:
    item = combo.model().item(index)
    item.setEnabled(enabled)
    item.setToolTip(tooltip)


class ParameterFormView(QWidget):
    """Collects every parameter GEE needs to fetch data, validates and keeps it."""

    request_kept = pyqtSignal(object)  # FormDTO

    def __init__(self, facade: IBusinessFacade, parent=None):
        super().__init__(parent)
        self._facade = facade
        self._imported_aoi: str = ""
        self._imported_name: str = ""
        self._drawn_aoi: str = ""  # GeoJSON of the rectangle / circle / polygon on the map
        self._drawn_name: str = ""
        self._error_labels: dict[str, QLabel] = {}

        self.setObjectName("ParameterForm")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(theme.FORM_STYLESHEET)

        content = QWidget()
        content.setObjectName("ParameterFormContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 8, 18, 18)
        content_layout.setSpacing(10)
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
        self.submit_button.setObjectName("PrimaryButton")
        self.submit_button.setDefault(True)
        for button in (self.reset_button, self.submit_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)

        action_bar = QWidget()
        action_bar.setObjectName("FormActionBar")
        action_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        buttons = QHBoxLayout(action_bar)
        buttons.setContentsMargins(18, 10, 18, 10)
        buttons.addWidget(self.status_label, 1)
        buttons.addWidget(self.reset_button)
        buttons.addWidget(self.submit_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(scroll, 1)
        layout.addWidget(action_bar)

        self.dataset_combo.currentIndexChanged.connect(self._on_dataset_changed)
        self.analysis_combo.currentIndexChanged.connect(self._on_analysis_changed)
        self._aoi_mode.idClicked.connect(self._on_aoi_mode_changed)
        self.import_button.clicked.connect(self._on_import_geojson)
        self.map_widget.bbox_drawn.connect(self._on_map_bbox_drawn)
        self.map_widget.circle_drawn.connect(self._on_map_circle_drawn)
        self.map_widget.polygon_drawn.connect(self._on_map_polygon_drawn)
        self.map_widget.shape_cleared.connect(self._on_map_shape_cleared)
        for spin in self._bbox_spins:
            spin.editingFinished.connect(self._on_bbox_typed)
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

        # Datasets grouped under non-selectable category headers.
        self.dataset_combo = QComboBox()
        header_font = QFont()
        header_font.setBold(True)
        for category, datasets in datasets_by_category().items():
            self.dataset_combo.addItem(category)
            header = self.dataset_combo.model().item(self.dataset_combo.count() - 1)
            header.setEnabled(False)
            header.setFont(header_font)
            for info in datasets:
                self.dataset_combo.addItem(f"    {info.name}", info.key)
                self.dataset_combo.setItemData(
                    self.dataset_combo.count() - 1, info.collection_id, Qt.ItemDataRole.ToolTipRole
                )

        self.dataset_info_label = QLabel()
        self.dataset_info_label.setStyleSheet(HINT_STYLE)
        self.dataset_info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.bands_list = QListWidget()
        self.bands_list.setMinimumHeight(150)
        self.bands_list.setMaximumHeight(180)

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
        form.addRow("", self.dataset_info_label)
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

        # Either a GeoJSON file OR a shape drawn on the map (rectangle, circle, polygon).
        self.aoi_file_radio = QRadioButton("GeoJSON file")
        self.aoi_draw_radio = QRadioButton("Draw on map (rectangle, circle or polygon)")
        self._aoi_mode = QButtonGroup(self)
        self._aoi_mode.addButton(self.aoi_file_radio, AOI_FILE)
        self._aoi_mode.addButton(self.aoi_draw_radio, AOI_DRAW)
        modes = QHBoxLayout()
        modes.addWidget(self.aoi_file_radio)
        modes.addWidget(self.aoi_draw_radio)
        modes.addStretch(1)

        self.map_widget = AoiMapWidget()
        self.map_widget.setMinimumHeight(340)

        # page 0: GeoJSON import
        file_page = QWidget()
        file_layout = QHBoxLayout(file_page)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.import_button = QPushButton("Import GeoJSON…")
        self.aoi_file_label = QLabel("No file imported.")
        self.aoi_file_label.setWordWrap(True)
        file_layout.addWidget(self.import_button)
        file_layout.addWidget(self.aoi_file_label, 1)

        # page 1: drawn shape summary + bounding box (the shape's extent; typing
        # coordinates replaces the shape with that rectangle)
        bbox_page = QWidget()
        bbox_layout = QVBoxLayout(bbox_page)
        bbox_layout.setContentsMargins(0, 0, 0, 0)
        self.shape_label = QLabel(NO_SHAPE_TEXT)
        self.shape_label.setWordWrap(True)
        hint = QLabel(
            "Pick a tool at the top-left of the map to draw a rectangle, circle or polygon. "
            "The boxes below show the shape's extent (WGS84 degrees); typing values draws that rectangle instead."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(HINT_STYLE)
        grid = QGridLayout()

        def coord_spin(limit: float) -> QDoubleSpinBox:
            spin = QDoubleSpinBox()
            spin.setRange(-limit, limit)
            spin.setDecimals(6)
            spin.setSingleStep(0.01)
            return spin

        self.min_lon_spin, self.max_lon_spin = coord_spin(180), coord_spin(180)
        self.min_lat_spin, self.max_lat_spin = coord_spin(90), coord_spin(90)
        self._bbox_spins = (self.min_lon_spin, self.min_lat_spin, self.max_lon_spin, self.max_lat_spin)
        grid.addWidget(QLabel("West (min lon):"), 0, 0)
        grid.addWidget(self.min_lon_spin, 0, 1)
        grid.addWidget(QLabel("East (max lon):"), 0, 2)
        grid.addWidget(self.max_lon_spin, 0, 3)
        grid.addWidget(QLabel("South (min lat):"), 1, 0)
        grid.addWidget(self.min_lat_spin, 1, 1)
        grid.addWidget(QLabel("North (max lat):"), 1, 2)
        grid.addWidget(self.max_lat_spin, 1, 3)
        bbox_layout.addWidget(self.shape_label)
        bbox_layout.addWidget(hint)
        bbox_layout.addLayout(grid)

        self.aoi_stack = QStackedWidget()
        self.aoi_stack.addWidget(file_page)
        self.aoi_stack.addWidget(bbox_page)

        layout.addLayout(modes)
        layout.addWidget(self.map_widget)
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
        self.analysis_combo.addItems(ANALYSIS_CATEGORIES.keys())
        self.processes_list = QListWidget()
        self.processes_list.setMinimumHeight(130)
        self.processes_list.setMaximumHeight(160)
        hint = QLabel("Greyed-out options are not available for the selected dataset.")
        hint.setStyleSheet(HINT_STYLE)
        form.addRow("Analysis type:", self.analysis_combo)
        form.addRow("", self._error_label("analysis_type"))
        form.addRow("Processes:", self.processes_list)
        form.addRow("", self._error_label("processes"))
        form.addRow("", hint)
        return group

    # ------------------------------------------------------------- behaviour
    def reset(self) -> None:
        today = QDate.currentDate()
        self.end_date_edit.setDate(today)
        self.start_date_edit.setDate(today.addMonths(-3))

        self.dataset_combo.setCurrentIndex(self.dataset_combo.findData("sentinel2_sr"))
        self._on_dataset_changed()

        self._imported_aoi = ""
        self._imported_name = ""
        self.aoi_file_label.setText("No file imported.")
        self.map_widget.show_geojson("")
        self._clear_drawn_shape()
        self.map_widget.clear_shape()
        self.aoi_file_radio.setChecked(True)
        self._on_aoi_mode_changed(AOI_FILE)

        self._show_validation(ValidationDTO())
        self.status_label.clear()

    def _current_dataset(self) -> DatasetInfo | None:
        return get_dataset(self.dataset_combo.currentData())

    def _on_dataset_changed(self) -> None:
        info = self._current_dataset()
        if info is None:
            return

        until = info.max_date.isoformat() if info.max_date else "present"
        self.dataset_info_label.setText(f"{info.collection_id}  ·  available {info.min_date.isoformat()} → {until}")

        self.bands_list.clear()
        for band in info.bands:
            _add_check_item(self.bands_list, band, checked=band in info.default_bands)
        self.scale_spin.setValue(info.default_scale)
        self.composite_combo.setCurrentText(info.default_composite)

        self.cloud_spin.setEnabled(info.supports_cloud_filter)
        self.cloud_spin.setValue(20 if info.supports_cloud_filter else 0)

        self._apply_date_limits(info)
        self._apply_analysis_compatibility(info)

    def _apply_date_limits(self, info: DatasetInfo) -> None:
        lowest = _qdate(info.min_date)
        highest = _qdate(info.max_date) if info.max_date else QDate.currentDate()
        for edit in (self.start_date_edit, self.end_date_edit):
            edit.setDateRange(lowest, highest)  # out-of-range values are clamped
        if self.start_date_edit.date() >= self.end_date_edit.date():
            self.start_date_edit.setDate(self.end_date_edit.date().addMonths(-3))

    def _apply_analysis_compatibility(self, info: DatasetInfo) -> None:
        """Grey out analysis types the dataset cannot support (UC-03 8c)."""
        self.analysis_combo.blockSignals(True)
        first_enabled = -1
        for i in range(self.analysis_combo.count()):
            category = self.analysis_combo.itemText(i)
            enabled = category in info.supported_analyses
            tooltip = "" if enabled else f"Not available for {info.name}"
            _set_combo_item_enabled(self.analysis_combo, i, enabled, tooltip)
            if enabled and first_enabled < 0:
                first_enabled = i
        if self.analysis_combo.currentText() not in info.supported_analyses:
            self.analysis_combo.setCurrentIndex(first_enabled)
        self.analysis_combo.blockSignals(False)
        self._on_analysis_changed()

    def _on_analysis_changed(self) -> None:
        """List every process of the category; grey out the unsupported ones."""
        info = self._current_dataset()
        category = self.analysis_combo.currentText()
        supported = info.supported_analyses.get(category, ()) if info else ()
        previously_checked = set(_checked_items(self.processes_list))

        self.processes_list.clear()
        for process in ANALYSIS_CATEGORIES.get(category, ()):
            enabled = process in supported
            _add_check_item(
                self.processes_list,
                process,
                checked=process in previously_checked,
                enabled=enabled,
                tooltip="" if enabled or info is None else f"Not available for {info.name}",
            )

    # ------------------------------------------------------------------- AOI
    def _on_aoi_mode_changed(self, mode: int) -> None:
        self.aoi_stack.setCurrentIndex(mode)
        self.map_widget.set_mode("draw" if mode == AOI_DRAW else "file")
        self._set_field_error("aoi", "")

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
            self.map_widget.show_geojson("")
            self._set_field_error("aoi", str(exc))
            return

        self._imported_aoi = aoi
        self._imported_name = Path(path).name
        geometry = json.loads(aoi)
        min_lon, min_lat, max_lon, max_lat = bbox_of(geometry)
        self.aoi_file_label.setText(
            f"<b>{self._imported_name}</b> · {geometry['type']}<br>"
            f"Extent: lon {min_lon:.4f} → {max_lon:.4f}, lat {min_lat:.4f} → {max_lat:.4f}"
        )
        self.map_widget.show_geojson(aoi)
        self._set_field_error("aoi", "")

    def _set_bbox_spins(self, min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> None:
        for spin, value in zip(self._bbox_spins, (min_lon, min_lat, max_lon, max_lat)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    def _bbox_values(self) -> tuple[float, float, float, float]:
        lon_a, lat_a, lon_b, lat_b = (s.value() for s in self._bbox_spins)
        return min(lon_a, lon_b), min(lat_a, lat_b), max(lon_a, lon_b), max(lat_a, lat_b)

    def _set_drawn_shape(self, geometry: dict, name: str, summary: str, sync_spins: bool = True) -> None:
        self._drawn_aoi = json.dumps(geometry)
        self._drawn_name = name
        self.shape_label.setText(summary)
        if sync_spins:
            min_lon, min_lat, max_lon, max_lat = bbox_of(geometry)
            self._set_bbox_spins(max(min_lon, -180), max(min_lat, -90), min(max_lon, 180), min(max_lat, 90))
        self._set_field_error("aoi", "")

    def _clear_drawn_shape(self) -> None:
        self._drawn_aoi = ""
        self._drawn_name = ""
        self.shape_label.setText(NO_SHAPE_TEXT)
        self._set_bbox_spins(0.0, 0.0, 0.0, 0.0)

    def _on_map_bbox_drawn(self, min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> None:
        min_lon, min_lat = max(min_lon, -180), max(min_lat, -90)
        max_lon, max_lat = min(max_lon, 180), min(max_lat, 90)
        self._set_drawn_shape(
            bbox_polygon(min_lon, min_lat, max_lon, max_lat), "Rectangle", "<b>Rectangle</b> drawn on the map."
        )

    def _on_map_circle_drawn(self, lon: float, lat: float, radius_m: float) -> None:
        radius = format_distance(radius_m)
        self._set_drawn_shape(
            circle_polygon(lon, lat, radius_m),
            f"Circle (r = {radius})",
            f"<b>Circle</b> · centre {lon:.4f}, {lat:.4f} · radius {radius}",
        )

    def _on_map_polygon_drawn(self, geometry_text: str) -> None:
        try:
            geometry = polygon_from_geojson(geometry_text)
            vertices = vertex_count(geometry)
        except (ValueError, KeyError, TypeError, IndexError, AttributeError):
            self._clear_drawn_shape()
            self._set_field_error("aoi", "Could not read the polygon drawn on the map. Please draw it again.")
            return
        self._set_drawn_shape(geometry, f"Polygon ({vertices} vertices)", f"<b>Polygon</b> · {vertices} vertices")

    def _on_map_shape_cleared(self) -> None:
        self._clear_drawn_shape()

    def _on_bbox_typed(self) -> None:
        min_lon, min_lat, max_lon, max_lat = self._bbox_values()
        if min_lon < max_lon and min_lat < max_lat:
            self._set_drawn_shape(
                bbox_polygon(min_lon, min_lat, max_lon, max_lat),
                "Rectangle",
                "<b>Rectangle</b> from the typed coordinates.",
                sync_spins=False,
            )
            self.map_widget.set_bbox(min_lon, min_lat, max_lon, max_lat, fit=True)

    # ---------------------------------------------------------------- submit
    def collect_form(self) -> FormDTO:
        """Build a FormDTO from the current widget values."""
        if self.aoi_file_radio.isChecked():
            aoi, aoi_name = self._imported_aoi, self._imported_name
        else:
            aoi, aoi_name = self._drawn_aoi, self._drawn_name

        return FormDTO(
            dataset=self.dataset_combo.currentData() or "",
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
