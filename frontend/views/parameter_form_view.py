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
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.business.facade import IBusinessFacade
from backend.config import (
    ANALYSIS_CATEGORIES,
    BYTES_PER_PIXEL,
    COMPOSITE_METHODS,
    CRS_OPTIONS,
    DEFAULT_DOWNLOAD_DIR,
    GEE_MAX_GRID_DIMENSION,
    GEE_MAX_REQUEST_BYTES,
    GEE_REQUEST_BYTES_PER_PIXEL,
    DatasetInfo,
    datasets_by_category,
    get_dataset,
)
from backend.dto import FormDTO, ValidationDTO
from backend.config.limits import MAX_QUERY_LENGTH
from backend.exceptions import GeeAssistError
from frontend import form_theme as theme
from frontend.aoi_geometry import (
    bbox_of,
    estimate_download,
    bbox_polygon,
    circle_polygon,
    format_bytes,
    format_distance,
    polygon_from_geojson,
    vertex_count,
)
from frontend.widgets.aoi_map_widget import AoiMapWidget
from frontend.widgets.query_assistant import QueryAssistant
from frontend.widgets.form_parts import (
    CheckComboBox,
    CheckGrid,
    StatusBanner,
    field_row,
    hint_label,
    labelled,
    pad_spin_text,
    section_card,
    set_invalid,
)
from frontend.workers.task_worker import run_task

AOI_FILE, AOI_DRAW = 0, 1
NO_SHAPE_TEXT = "No shape drawn yet."
NO_FILE_TEXT = "No file imported."
NO_ANALYSIS_TEXT = "None (download only)"
PROCESS_COLUMNS = 2


# ---------------------------------------------------------------------- helpers
def _qdate(value) -> QDate:
    return QDate(value.year, value.month, value.day)


def _set_combo_item_enabled(combo: QComboBox, index: int, enabled: bool, tooltip: str = "") -> None:
    item = combo.model().item(index)
    item.setEnabled(enabled)
    item.setToolTip(tooltip)


def _segment_button(text: str, position: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("SegmentButton")
    button.setProperty("segment", position)
    button.setCheckable(True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


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
        self._error_targets: dict[str, tuple[QWidget, ...]] = {}

        self.setObjectName("ParameterForm")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(theme.FORM_STYLESHEET)

        # ---- page heading
        title = QLabel("Parameter Form")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Tell Google Earth Engine what to fetch: the dataset, the area, the time range and the analysis.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        # ---- time range and output share one row
        time_and_output = QHBoxLayout()
        time_and_output.setSpacing(14)
        time_and_output.addWidget(self._build_time_group(), 2)
        time_and_output.addWidget(self._build_output_group(), 3)

        content = QWidget()
        content.setObjectName("ParameterFormContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 18, 22, 22)
        content_layout.setSpacing(14)
        content_layout.addWidget(title)
        content_layout.addWidget(subtitle)
        content_layout.addSpacing(2)
        content_layout.addWidget(self._build_dataset_group())
        content_layout.addWidget(self._build_aoi_group())
        content_layout.addLayout(time_and_output)
        content_layout.addWidget(self._build_analysis_group())
        content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)

        # ---- action bar
        self.status_banner = StatusBanner()
        self.reset_button = QPushButton("Reset")
        self.reset_button.setObjectName("SecondaryButton")
        self.submit_button = QPushButton("Submit Parameters")
        self.submit_button.setObjectName("PrimaryButton")
        self.submit_button.setDefault(True)
        for button in (self.reset_button, self.submit_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(40)

        action_bar = QWidget()
        action_bar.setObjectName("FormActionBar")
        action_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        buttons = QHBoxLayout(action_bar)
        buttons.setContentsMargins(22, 10, 22, 10)
        buttons.setSpacing(10)
        buttons.addWidget(self.status_banner, 1)
        buttons.addStretch(0)
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
        pad_spin_text(self.scale_spin, self.cloud_spin, *self._bbox_spins)
        self.browse_button.clicked.connect(self._on_browse_output)
        self.output_dir_edit.textEdited.connect(lambda _: self._set_field_error("output_dir", ""))
        self.bands_combo.selection_changed.connect(self._update_estimate)
        self.scale_spin.valueChanged.connect(self._update_estimate)
        self.reset_button.clicked.connect(self.reset)
        self.submit_button.clicked.connect(self._on_submit)

        # Natural-language assistant (UC-02): fills this form via Gemini. The
        # main window places it in the side panel, under the kept requests.
        self.assistant = QueryAssistant(MAX_QUERY_LENGTH)
        self.assistant.submitted.connect(self._on_query_submitted)

        self.reset()

    # ------------------------------------------------------------------ build
    def _error_label(self, key: str, *targets: QWidget) -> QLabel:
        """Red message under a field; ``targets`` get a red border while it is shown."""
        label = QLabel()
        label.setObjectName("FieldError")
        label.setWordWrap(True)
        label.hide()
        self._error_labels[key] = label
        self._error_targets[key] = targets
        return label

    def _build_dataset_group(self) -> QFrame:
        card, body = section_card("Dataset", "Satellite collection, bands and how the images are combined.")

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
        self.dataset_info_label = hint_label()
        self.dataset_info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

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

        self.bands_combo = CheckComboBox(placeholder="No bands selected")

        body.addWidget(labelled(
            "Dataset", self.dataset_combo, self.dataset_info_label,
            self._error_label("dataset", self.dataset_combo),
        ))
        body.addLayout(field_row(
            labelled("Bands", self.bands_combo, self._error_label("bands", self.bands_combo)),
            labelled("Scale", self.scale_spin, self._error_label("scale", self.scale_spin)),
            labelled("Max cloud cover", self.cloud_spin, self._error_label("max_cloud_cover", self.cloud_spin)),
            labelled("Composite", self.composite_combo, self._error_label("composite", self.composite_combo)),
            stretches=(5, 3, 3, 3),
        ))
        return card

    def _build_aoi_group(self) -> QFrame:
        card, body = section_card(
            "Area of Interest", "Import a boundary file, or draw a rectangle, circle or polygon on the map."
        )

        # Either a GeoJSON file OR a shape drawn on the map.
        self.aoi_file_toggle = _segment_button("GeoJSON file", "first")
        self.aoi_draw_toggle = _segment_button("Draw on map", "last")
        self._aoi_mode = QButtonGroup(self)
        self._aoi_mode.setExclusive(True)
        self._aoi_mode.addButton(self.aoi_file_toggle, AOI_FILE)
        self._aoi_mode.addButton(self.aoi_draw_toggle, AOI_DRAW)

        # GeoJSON page: import button + summary, on the same row as the toggle
        file_page = QWidget()
        file_layout = QHBoxLayout(file_page)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(12)
        self.import_button = QPushButton("Import GeoJSON…")
        self.import_button.setObjectName("SecondaryButton")
        self.import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.aoi_file_label = QLabel(NO_FILE_TEXT)
        self.aoi_file_label.setWordWrap(True)
        file_layout.addWidget(self.import_button)
        file_layout.addWidget(self.aoi_file_label, 1)

        # Draw page: shape summary on the toggle row
        draw_page = QWidget()
        draw_layout = QHBoxLayout(draw_page)
        draw_layout.setContentsMargins(0, 0, 0, 0)
        self.shape_label = QLabel(NO_SHAPE_TEXT)
        self.shape_label.setWordWrap(True)
        draw_layout.addWidget(self.shape_label, 1)

        self.aoi_summary_stack = QStackedWidget()
        self.aoi_summary_stack.addWidget(file_page)
        self.aoi_summary_stack.addWidget(draw_page)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(0)
        toggle_row.addWidget(self.aoi_file_toggle)
        toggle_row.addWidget(self.aoi_draw_toggle)
        toggle_row.addSpacing(16)
        toggle_row.addWidget(self.aoi_summary_stack, 1)

        self.map_widget = AoiMapWidget()
        self.map_widget.setMinimumHeight(360)

        # Bounding-box coordinates (draw mode only): all four on one row.
        def coord_spin(limit: float) -> QDoubleSpinBox:
            spin = QDoubleSpinBox()
            spin.setRange(-limit, limit)
            spin.setDecimals(6)
            spin.setSingleStep(0.01)
            return spin

        self.min_lon_spin, self.max_lon_spin = coord_spin(180), coord_spin(180)
        self.min_lat_spin, self.max_lat_spin = coord_spin(90), coord_spin(90)
        self._bbox_spins = (self.min_lon_spin, self.min_lat_spin, self.max_lon_spin, self.max_lat_spin)

        self.coords_box = QWidget()
        coords_layout = QVBoxLayout(self.coords_box)
        coords_layout.setContentsMargins(0, 0, 0, 0)
        coords_layout.setSpacing(6)
        coords_layout.addLayout(field_row(
            labelled("West (min lon)", self.min_lon_spin),
            labelled("South (min lat)", self.min_lat_spin),
            labelled("East (max lon)", self.max_lon_spin),
            labelled("North (max lat)", self.max_lat_spin),
        ))
        coords_layout.addWidget(hint_label(
            "Extent of the drawn shape in WGS84 degrees. Typing values replaces the shape with that rectangle."
        ))

        body.addLayout(toggle_row)
        body.addWidget(self.map_widget)
        body.addWidget(self.coords_box)
        body.addWidget(self._error_label("aoi"))
        return card

    def _build_time_group(self) -> QFrame:
        card, body = section_card("Time Range", "Images acquired between these dates are used.")

        def date_edit() -> QDateEdit:
            edit = QDateEdit()
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
            return edit

        self.start_date_edit = date_edit()
        self.end_date_edit = date_edit()
        self.date_hint_label = hint_label()
        body.addLayout(field_row(
            labelled("Start date", self.start_date_edit),
            labelled("End date", self.end_date_edit),
        ))
        body.addWidget(self._error_label("dates", self.start_date_edit, self.end_date_edit))
        body.addWidget(self.date_hint_label)
        body.addStretch(1)
        return card

    def _build_output_group(self) -> QFrame:
        card, body = section_card("Output", "Where the GeoTIFF is saved and in which projection.")

        self.crs_combo = QComboBox()
        for code, label in CRS_OPTIONS:
            self.crs_combo.addItem(label, code)
        self.crs_combo.setToolTip(
            "WGS 84 keeps longitude/latitude. A UTM zone uses metres, which suits area measurements."
        )

        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setObjectName("PathField")
        self.output_dir_edit.setPlaceholderText("Folder for the downloaded files")
        self.browse_button = QPushButton("Browse…")
        self.browse_button.setObjectName("SecondaryButton")
        self.browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        folder_row.addWidget(self.output_dir_edit, 1)
        folder_row.addWidget(self.browse_button)

        self.estimate_label = hint_label()

        body.addWidget(labelled("Projection (CRS)", self.crs_combo, self._error_label("crs", self.crs_combo)))
        body.addWidget(labelled(
            "Save to folder", folder_row, self._error_label("output_dir", self.output_dir_edit)
        ))
        body.addWidget(self.estimate_label)
        body.addStretch(1)
        return card

    def _build_analysis_group(self) -> QFrame:
        card, body = section_card(
            "Analysis (optional)",
            "Leave as None to only download the data. Greyed-out options do not suit the selected dataset.",
        )
        self.analysis_combo = QComboBox()
        self.analysis_combo.addItem(NO_ANALYSIS_TEXT, "")
        for category in ANALYSIS_CATEGORIES:
            self.analysis_combo.addItem(category, category)
        self.processes_grid = CheckGrid(PROCESS_COLUMNS)
        self.processes_field = labelled(
            "Processes", self.processes_grid, self._error_label("processes", self.processes_grid)
        )
        body.addLayout(field_row(
            labelled("Analysis type", self.analysis_combo, self._error_label("analysis_type", self.analysis_combo)),
            self.processes_field,
            stretches=(2, 3),
        ))
        return card

    # ------------------------------------------------------------- behaviour
    def reset(self) -> None:
        today = QDate.currentDate()
        self.end_date_edit.setDate(today)
        self.start_date_edit.setDate(today.addMonths(-3))

        self.dataset_combo.setCurrentIndex(self.dataset_combo.findData("sentinel2_sr"))
        self._on_dataset_changed()

        self._imported_aoi = ""
        self._imported_name = ""
        self.aoi_file_label.setText(NO_FILE_TEXT)
        self.map_widget.show_geojson("")
        self._clear_drawn_shape()
        self.map_widget.clear_shape()
        self.aoi_file_toggle.setChecked(True)
        self._on_aoi_mode_changed(AOI_FILE)

        self.crs_combo.setCurrentIndex(0)
        self.output_dir_edit.setText(str(DEFAULT_DOWNLOAD_DIR))
        self.analysis_combo.setCurrentIndex(0)  # None: download only

        self._show_validation(ValidationDTO())
        self.status_banner.clear()

    def _current_dataset(self) -> DatasetInfo | None:
        return get_dataset(self.dataset_combo.currentData())

    def _on_dataset_changed(self) -> None:
        info = self._current_dataset()
        if info is None:
            return

        until = info.max_date.isoformat() if info.max_date else "present"
        self.dataset_info_label.setText(f"{info.collection_id}  ·  available {info.min_date.isoformat()} → {until}")
        self.date_hint_label.setText(f"{info.name} is available from {info.min_date.isoformat()} to {until}.")

        self.bands_combo.set_items([(band, band in info.default_bands) for band in info.bands])
        self.scale_spin.setValue(info.default_scale)
        self.composite_combo.setCurrentText(info.default_composite)

        self.cloud_spin.setEnabled(info.supports_cloud_filter)
        self.cloud_spin.setValue(20 if info.supports_cloud_filter else 0)
        self.cloud_spin.setToolTip(
            "Scenes with more cloud cover than this are excluded."
            if info.supports_cloud_filter else f"{info.name} has no cloud-cover filter."
        )

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
        for i in range(1, self.analysis_combo.count()):  # item 0 ("None") always stays available
            category = self.analysis_combo.itemData(i)
            enabled = category in info.supported_analyses
            tooltip = "" if enabled else f"Not available for {info.name}"
            _set_combo_item_enabled(self.analysis_combo, i, enabled, tooltip)
        if self.analysis_combo.currentData() and self.analysis_combo.currentData() not in info.supported_analyses:
            self.analysis_combo.setCurrentIndex(0)  # fall back to download only
        self.analysis_combo.blockSignals(False)
        self._on_analysis_changed()

    def _on_analysis_changed(self) -> None:
        """List every process of the category; grey out the unsupported ones."""
        info = self._current_dataset()
        category = self.analysis_combo.currentData() or ""
        self.processes_field.setVisible(bool(category))
        supported = info.supported_analyses.get(category, ()) if info else ()
        previously_checked = set(self.processes_grid.checked())

        self.processes_grid.set_items([
            (
                process,
                process in previously_checked,
                process in supported,
                "" if process in supported or info is None else f"Not available for {info.name}",
            )
            for process in ANALYSIS_CATEGORIES.get(category, ())
        ])

    # ------------------------------------------------------------------- AOI
    def _on_aoi_mode_changed(self, mode: int) -> None:
        self.aoi_summary_stack.setCurrentIndex(mode)
        self.coords_box.setVisible(mode == AOI_DRAW)
        self.map_widget.set_mode("draw" if mode == AOI_DRAW else "file")
        self._set_field_error("aoi", "")
        self._update_estimate()

    def _on_import_geojson(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import GeoJSON", "", "GeoJSON files (*.geojson *.json);;All files (*)"
        )
        if not path:  # 6c: user cancelled
            return
        try:
            self.import_geojson(path)
        except GeeAssistError:
            pass  # shown under the area

    def import_geojson(self, path: str) -> None:
        """UC-04: read a GeoJSON file into the form. Raises the import error after showing it."""
        try:
            aoi = self._facade.import_aoi(path)
        except GeeAssistError as exc:  # 6a / 6b
            self._imported_aoi = ""
            self.aoi_file_label.setText(NO_FILE_TEXT)
            self.map_widget.show_geojson("")
            self._set_field_error("aoi", str(exc))
            self._update_estimate()
            raise
        self.set_imported_area(aoi, Path(path).name)

    def set_imported_area(self, aoi: str, name: str) -> None:
        """Show ``aoi`` (GeoJSON) as the imported file's area and switch to "GeoJSON file"."""
        self._imported_aoi = aoi
        self._imported_name = name
        geometry = json.loads(aoi)
        min_lon, min_lat, max_lon, max_lat = bbox_of(geometry)
        self.aoi_file_label.setText(
            f"<b>{self._imported_name}</b> · {geometry['type']}<br>"
            f"Extent: lon {min_lon:.4f} → {max_lon:.4f}, lat {min_lat:.4f} → {max_lat:.4f}"
        )
        self.aoi_file_toggle.setChecked(True)
        self._on_aoi_mode_changed(AOI_FILE)
        self.map_widget.show_geojson(aoi)
        self._set_field_error("aoi", "")
        self._update_estimate()

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
        self._update_estimate()

    def _clear_drawn_shape(self) -> None:
        self._drawn_aoi = ""
        self._drawn_name = ""
        self.shape_label.setText(NO_SHAPE_TEXT)
        self._set_bbox_spins(0.0, 0.0, 0.0, 0.0)
        self._update_estimate()

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

    # ------------------------------------------------------- natural language
    def _on_query_submitted(self, text: str) -> None:
        self.assistant.set_busy(True)
        run_task(
            self, self._facade.submit_query, text,
            on_success=self._on_query_interpreted, on_error=self._on_query_failed,
        )

    def _on_query_interpreted(self, form: FormDTO) -> None:
        self.assistant.set_busy(False)
        filled = self.apply_form(form)
        notes = " ".join(form.notes)

        if not filled:
            self.assistant.show_info(
                form.clarification
                or "No form values could be taken from that request. Try naming a place, dates or a dataset."
            )
            return

        recognised = list(dict.fromkeys(e.text for e in form.entities))
        summary = " ".join(filter(None, (
            f"Recognised: {' · '.join(recognised)}." if recognised else "",
            f"Filled: {', '.join(filled)}.",
        )))
        if form.clarification:  # partly understood: keep the card open with Gemini's question
            self.assistant.show_info(f"{summary} {form.clarification}")
        else:
            self.assistant.collapse()
        self.status_banner.show_info(" ".join(filter(None, (summary, notes, "Check the values, then press Submit Parameters."))))

    def _on_query_failed(self, exc: Exception) -> None:
        self.assistant.set_busy(False)
        self.assistant.show_error(str(exc) if isinstance(exc, GeeAssistError) else "Something went wrong. Please try again.")

    def apply_form(self, form: FormDTO) -> list[str]:
        """Put the values of ``form`` into the widgets. Returns the names of the parts filled.

        Empty values leave the current field untouched; the output settings
        (projection, folder) are never changed by a query.
        """
        filled: list[str] = []
        self._show_validation(ValidationDTO())  # clear old errors

        index = self.dataset_combo.findData(form.dataset) if form.dataset else -1
        if index >= 0:
            self.dataset_combo.setCurrentIndex(index)
            self._on_dataset_changed()  # also when it was already selected: resets dependent fields
            filled.append("dataset")
            if form.bands:
                self.bands_combo.set_checked(form.bands)
                filled.append("bands")
            if form.scale:
                self.scale_spin.setValue(form.scale)
            if form.max_cloud_cover is not None and self.cloud_spin.isEnabled():
                self.cloud_spin.setValue(form.max_cloud_cover)
                filled.append("cloud cover")
            if form.composite:
                self.composite_combo.setCurrentText(form.composite)

        if form.start_date or form.end_date:
            if form.end_date:
                self.end_date_edit.setDate(_qdate(form.end_date))
            if form.start_date:
                self.start_date_edit.setDate(_qdate(form.start_date))
            filled.append("dates")

        if form.aoi:
            geometry = json.loads(form.aoi)
            name = form.aoi_name or "Area from your request"
            self.aoi_draw_toggle.setChecked(True)
            self._on_aoi_mode_changed(AOI_DRAW)
            self._set_drawn_shape(
                geometry, name,
                f"<b>{name}</b> · approximate area from your request. Adjust it on the map if needed.",
            )
            min_lon, min_lat, max_lon, max_lat = bbox_of(geometry)
            self.map_widget.set_bbox(min_lon, min_lat, max_lon, max_lat, fit=True)
            filled.append(f"area ({name})")

        analysis_index = self.analysis_combo.findData(form.analysis_type) if form.analysis_type else -1
        if analysis_index > 0 and self.analysis_combo.model().item(analysis_index).isEnabled():
            self.analysis_combo.setCurrentIndex(analysis_index)
            self._on_analysis_changed()
            self.processes_grid.set_checked(form.processes)
            filled.append("analysis")

        return filled

    # ---------------------------------------------------------------- output
    def _on_browse_output(self) -> None:
        start = self.output_dir_edit.text().strip() or str(DEFAULT_DOWNLOAD_DIR)
        folder = QFileDialog.getExistingDirectory(self, "Choose download folder", start)
        if folder:  # empty when the user cancels
            self.output_dir_edit.setText(str(Path(folder)))
            self._set_field_error("output_dir", "")

    def _update_estimate(self, *_args) -> None:
        """Rough GeoTIFF size and how many GEE requests (tiles) the download needs."""
        if not hasattr(self, "estimate_label"):
            return  # still building the form
        aoi, _name = self._current_aoi()
        bands = self.bands_combo.checked()
        if not aoi or not bands:
            self.estimate_label.setText("Size estimate appears once an area and at least one band are chosen.")
            return
        # Sizes are float32 (file size); GEE counts 5 bytes per pixel and band against its
        # request limit, so the limit is scaled to count requests the way GEE does.
        estimate = estimate_download(
            json.loads(aoi), self.scale_spin.value(), len(bands),
            BYTES_PER_PIXEL, GEE_MAX_REQUEST_BYTES * BYTES_PER_PIXEL // GEE_REQUEST_BYTES_PER_PIXEL,
            GEE_MAX_GRID_DIMENSION,
        )
        tiles = "1 request" if estimate.requests == 1 else f"{estimate.requests:,} tiles"
        self.estimate_label.setText(
            f"Estimated download: {estimate.width_px:,} × {estimate.height_px:,} px · "
            f"{len(bands)} band{'s' if len(bands) != 1 else ''} · ~{format_bytes(estimate.total_bytes)} "
            f"→ {tiles} (GEE allows {format_bytes(GEE_MAX_REQUEST_BYTES)} per request)."
        )

    # ---------------------------------------------------------------- submit
    def _current_aoi(self) -> tuple[str, str]:
        if self.aoi_file_toggle.isChecked():
            return self._imported_aoi, self._imported_name
        return self._drawn_aoi, self._drawn_name

    def collect_form(self) -> FormDTO:
        """Build a FormDTO from the current widget values."""
        aoi, aoi_name = self._current_aoi()

        return FormDTO(
            dataset=self.dataset_combo.currentData() or "",
            bands=self.bands_combo.checked(),
            scale=self.scale_spin.value(),
            max_cloud_cover=self.cloud_spin.value() if self.cloud_spin.isEnabled() else None,
            composite=self.composite_combo.currentText(),
            aoi=aoi,
            aoi_name=aoi_name,
            start_date=self.start_date_edit.date().toPyDate(),
            end_date=self.end_date_edit.date().toPyDate(),
            crs=self.crs_combo.currentData(),
            output_dir=self.output_dir_edit.text().strip(),
            analysis_type=self.analysis_combo.currentData() or "",
            processes=self.processes_grid.checked(),
            source="form",
        )

    def _on_submit(self) -> None:
        form = self.collect_form()
        try:
            result = self._facade.submit_form(form)
        except GeeAssistError as exc:
            self.status_banner.show_error(str(exc))
            return

        self._show_validation(result)
        if result.is_valid:
            self.request_kept.emit(form)

    def _show_validation(self, result: ValidationDTO) -> None:
        for key in self._error_labels:
            self._set_field_error(key, result.errors.get(key, ""))
        if result.is_valid:
            self.status_banner.show_success(result.message)
        else:
            self.status_banner.show_error(result.message)

    def _set_field_error(self, key: str, message: str) -> None:
        label = self._error_labels[key]
        label.setText(message)
        label.setVisible(bool(message))
        for target in self._error_targets.get(key, ()):
            set_invalid(target, bool(message))
