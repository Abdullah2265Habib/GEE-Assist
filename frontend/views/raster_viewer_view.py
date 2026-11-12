"""Viewer page: shows a downloaded GeoTIFF.

The file is read and drawn in the background (large downloads take a moment). The
right-hand panel picks the view (true colour, false colour, NDVI, NDWI, land-cover
classes, single bands), explains it with a legend, shows the values under the
pointer and the file's details. The picture zooms with the mouse wheel and pans by
dragging; double-click fits it to the window again. "Show on map" lays the current
view over the Query Input map.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QBuffer, QIODevice, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFontMetrics
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from backend.business.facade import IBusinessFacade
from backend.business.map.colour_maps import DYNAMIC_WORLD_CLASSES
from backend.dto.map_dto import RasterInfoDTO, RasterViewDTO, ViewPresetDTO
from backend.exceptions import GeeAssistError
from frontend import theme
from frontend.download_format import format_size
from frontend.widgets.form_parts import StatusBanner
from frontend.widgets.raster_canvas import RasterCanvas, rgba_to_image
from frontend.widgets.raster_legend import RasterLegend, format_value
from frontend.workers.task_worker import run_task

PANEL_WIDTH = 320
MAP_IMAGE_SIZE = 1024  # longer side of the picture sent to the map
HOVER_DELAY_MS = 40   # wait for the pointer to rest a moment before reading values

STYLESHEET = f"""
#ViewerPage {{ background: transparent; }}
QLabel#PageTitle {{ font-family: "{theme.SERIF}"; font-size: 20pt; color: {theme.INK}; }}
QLabel#PageSubtitle {{ color: {theme.MUTED}; }}
QFrame#ViewerCanvasCard, QFrame#ViewerPanel {{
    background: {theme.WHITE}; border: 1px solid {theme.BORDER}; border-radius: 12px;
}}
QFrame#ViewerPanel QLabel {{ background: transparent; }}
QLabel#SectionTitle {{ color: {theme.MUTED}; font-size: 8.5pt; font-weight: 600; letter-spacing: 0.5px; }}
QLabel#Value {{ color: {theme.INK}; }}
QComboBox {{
    background: {theme.FIELD_BG}; border: 1px solid {theme.BORDER_STRONG}; border-radius: 8px;
    padding: 6px 10px; color: {theme.INK};
}}
"""


def _section(title: str) -> QLabel:
    return QLabel(title.upper(), objectName="SectionTitle")


class ElidedLabel(QLabel):
    """One line of text shortened with "…" in the middle to fit (e.g. a long file path); all of it in the tooltip."""

    def __init__(self, parent: QWidget | None = None, **qt_properties):
        super().__init__(parent, **qt_properties)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_full_text(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._elide()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        self.setText(QFontMetrics(self.font()).elidedText(self._full, Qt.TextElideMode.ElideMiddle, self.width()))


class RasterViewerView(QWidget):
    show_on_map_requested = pyqtSignal(bytes, object, str)  # PNG, (west, south, east, north), title

    def __init__(self, facade: IBusinessFacade, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ViewerPage")
        self.setStyleSheet(STYLESHEET)
        self._facade = facade
        self.info: RasterInfoDTO | None = None
        self.view: RasterViewDTO | None = None
        self._presets: list[ViewPresetDTO] = []
        self._pointer: tuple[float, float] | None = None

        # ---- header
        self.title = QLabel("Viewer", objectName="PageTitle")
        self.subtitle = QLabel(objectName="PageSubtitle")
        self.banner = StatusBanner()

        # ---- picture
        self.canvas = RasterCanvas()
        canvas_card = QFrame(objectName="ViewerCanvasCard")
        canvas_layout = QVBoxLayout(canvas_card)
        canvas_layout.setContentsMargins(6, 6, 6, 6)
        canvas_layout.addWidget(self.canvas)

        # ---- panel: view, legend, values, details
        self.preset_box = QComboBox()
        self.preset_box.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preset_note = QLabel(objectName="Muted")
        self.preset_note.setWordWrap(True)
        self.preset_note.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.legend = RasterLegend()
        self.pointer_label = QLabel("Point at the picture to see its values.", objectName="Muted")
        self.pointer_label.setWordWrap(True)
        self.values_grid = QGridLayout()
        self.values_grid.setHorizontalSpacing(12)
        self.values_grid.setVerticalSpacing(3)
        self.value_labels: dict[str, QLabel] = {}
        self.details_grid = QGridLayout()
        self.details_grid.setHorizontalSpacing(12)
        self.details_grid.setVerticalSpacing(4)
        self.detail_labels: dict[str, QLabel] = {}
        for row, (key, name) in enumerate((("size", "Size"), ("bands", "Bands"), ("crs", "Coordinates"),
                                           ("area", "Area"), ("file_size", "File size"), ("path", "File"))):
            value = ElidedLabel(objectName="Value") if key == "path" else QLabel(objectName="Value")
            value.setWordWrap(key != "path")
            value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)  # never widens the panel
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.details_grid.addWidget(QLabel(name, objectName="Muted"), row, 0, Qt.AlignmentFlag.AlignTop)
            self.details_grid.addWidget(value, row, 1)
            self.detail_labels[key] = value
        self.details_grid.setColumnStretch(1, 1)

        self.map_button = QPushButton("Show on map", objectName="PrimaryButton")
        self.map_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.map_button.setToolTip("Lay this view over the Query Input map")
        self.fit_button = QPushButton("Fit to window", objectName="SecondaryButton")
        self.folder_button = QPushButton("Open folder", objectName="SecondaryButton")
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(8)
        for button in (self.fit_button, self.folder_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.buttons.addWidget(button)

        panel_content = QWidget()
        column = QVBoxLayout(panel_content)
        column.setContentsMargins(18, 16, 18, 16)
        column.setSpacing(10)
        column.addWidget(_section("View"))
        column.addWidget(self.preset_box)
        column.addWidget(self.preset_note)
        column.addSpacing(6)
        column.addWidget(self.legend)
        column.addSpacing(6)
        column.addWidget(_section("Under the pointer"))
        column.addWidget(self.pointer_label)
        column.addLayout(self.values_grid)
        column.addSpacing(6)
        column.addWidget(_section("Details"))
        column.addLayout(self.details_grid)
        column.addStretch(1)
        column.addWidget(self.map_button)
        column.addLayout(self.buttons)
        panel_scroll = QScrollArea()
        panel_scroll.setWidgetResizable(True)
        panel_scroll.setFrameShape(QFrame.Shape.NoFrame)
        panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        panel_scroll.setWidget(panel_content)
        panel = QFrame(objectName="ViewerPanel")
        panel.setFixedWidth(PANEL_WIDTH)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(panel_scroll)

        body = QHBoxLayout()
        body.setSpacing(14)
        body.addWidget(canvas_card, 1)
        body.addWidget(panel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.banner)
        layout.addLayout(body, 1)

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(HOVER_DELAY_MS)
        self._hover_timer.timeout.connect(self._read_values)

        self.preset_box.currentIndexChanged.connect(self._on_preset_chosen)
        self.canvas.hovered.connect(self._on_hovered)
        self.canvas.left_image.connect(self._on_left_image)
        self.fit_button.clicked.connect(self.canvas.fit)
        self.folder_button.clicked.connect(self.open_folder)
        self.map_button.clicked.connect(self.show_on_map)
        self._set_ready(False)

    # ------------------------------------------------------------- opening
    def open(self, path: str) -> None:
        """Show the GeoTIFF at ``path`` (read in the background)."""
        self.info, self.view, self._presets = None, None, []
        self.canvas.clear()
        self.title.setText(Path(path).stem)
        self.subtitle.setText("")
        self._set_ready(False)
        self.banner.show_info("Reading the file…")
        run_task(self, self._facade.describe_raster, path, on_success=self._on_described, on_error=self._show_error)

    def _on_described(self, info: RasterInfoDTO) -> None:
        self.info = info
        self.subtitle.setText(_summary(info))
        self._fill_details(info)
        self._fill_value_rows(info)
        self._presets = self._facade.raster_view_presets(info)
        self.preset_box.blockSignals(True)
        self.preset_box.clear()
        for preset in self._presets:
            self.preset_box.addItem(preset.label, preset.key)
        self.preset_box.blockSignals(False)
        self._set_ready(True)
        self.show_preset(self._presets[0])

    def show_preset(self, preset: ViewPresetDTO) -> None:
        if self.info is None:
            return
        self.preset_box.blockSignals(True)
        self.preset_box.setCurrentIndex(self._presets.index(preset))
        self.preset_box.blockSignals(False)
        self.preset_note.setText(preset.description)
        self.banner.show_info(f"Drawing {preset.label.lower()}…")
        run_task(self, self._facade.render_raster, self.info, preset, on_success=self._on_rendered,
                 on_error=self._show_error)

    def _on_rendered(self, view: RasterViewDTO) -> None:
        same_file = self.view is not None and (self.view.width, self.view.height) == (view.width, view.height)
        self.view = view
        self.canvas.set_image(rgba_to_image(view.rgba), keep_view=same_file)
        self.legend.set_legend(view.legend)
        self.map_button.setEnabled(True)
        if view.notes:
            self.banner.show_info(" ".join(view.notes))
        else:
            self.banner.clear()
        if self._pointer is not None:
            self._read_values()  # the index or class under the pointer may have changed

    def _on_preset_chosen(self, index: int) -> None:
        if 0 <= index < len(self._presets):
            self.show_preset(self._presets[index])

    def _show_error(self, exc: Exception) -> None:
        self.banner.show_error(str(exc) if isinstance(exc, GeeAssistError) else "The file could not be shown.")

    def _set_ready(self, ready: bool) -> None:
        for widget in (self.preset_box, self.fit_button, self.folder_button):
            widget.setEnabled(ready)
        self.map_button.setEnabled(ready and self.view is not None)

    def show_on_map(self) -> None:
        """Ask for the current view to be laid over the map, where the file lies."""
        if self.info is None or self.view is None:
            return
        title = f"{self.info.name} · {self.view.preset.label}"
        self.show_on_map_requested.emit(self.map_png(), self.info.bounds, title)

    def map_png(self, max_size: int = MAP_IMAGE_SIZE) -> bytes:
        """The current view as PNG, at most ``max_size`` pixels on its longer side."""
        image = rgba_to_image(self.view.rgba)
        if max(image.width(), image.height()) > max_size:
            image = image.scaled(max_size, max_size, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        return bytes(buffer.data())

    def open_folder(self) -> None:
        if self.info is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.info.path).parent)))

    # ------------------------------------------------------------- values under the pointer
    def _on_hovered(self, x: float, y: float) -> None:
        self._pointer = (x, y)
        self._hover_timer.start()

    def _on_left_image(self) -> None:
        self._pointer = None
        self._hover_timer.stop()
        self.pointer_label.setText("Point at the picture to see its values.")
        for label in self.value_labels.values():
            label.setText("–")

    def lon_lat_at(self, x: float, y: float) -> tuple[float, float]:
        """The longitude and latitude of preview pixel (x, y).

        Exact for files in degrees (EPSG:4326, what downloads use); close for projected ones.
        """
        west, south, east, north = self.info.bounds
        return west + x / self.view.width * (east - west), north - y / self.view.height * (north - south)

    def _read_values(self) -> None:
        if self._pointer is None or self.info is None or self.view is None:
            return
        lon, lat = self.lon_lat_at(*self._pointer)
        try:
            values = self._facade.raster_values_at(self.info, lon, lat)
        except GeeAssistError as exc:
            self._show_error(exc)
            return
        self.pointer_label.setText(f"{lat:.5f}°, {lon:.5f}°" + self._view_value(values))
        for band, label in self.value_labels.items():
            label.setText(format_value(values.get(band)))

    def _view_value(self, values: dict[str, float | None]) -> str:
        """The current view's own value there: the index, or the land-cover class."""
        preset = self.view.preset
        if preset.kind == "index":
            a, b = (values.get(band) for band in preset.bands)
            if a is None or b is None or a + b == 0:
                return ""
            return f"\n{preset.label.split()[0]}: {format_value((a - b) / (a + b))}"
        if preset.kind == "classes":
            value = values.get(preset.bands[0])
            if value is not None and 0 <= int(value) < len(DYNAMIC_WORLD_CLASSES):
                return f"\n{DYNAMIC_WORLD_CLASSES[int(value)][0]}"
        return ""

    # ------------------------------------------------------------- details
    def _fill_details(self, info: RasterInfoDTO) -> None:
        west, south, east, north = info.bounds
        texts = {
            "size": f"{info.width:,} × {info.height:,} px",
            "bands": ", ".join(info.band_names),
            "crs": info.crs or "unknown",
            "area": f"{south:.4f}° to {north:.4f}° N\n{west:.4f}° to {east:.4f}° E",
            "file_size": format_size(info.size_bytes),
        }
        for key, text in texts.items():
            self.detail_labels[key].setText(text)
        self.detail_labels["path"].set_full_text(info.path)

    def _fill_value_rows(self, info: RasterInfoDTO) -> None:
        while self.values_grid.count():
            item = self.values_grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.value_labels = {}
        for row, band in enumerate(info.band_names):
            value = QLabel("–", objectName="Value")
            self.values_grid.addWidget(QLabel(band, objectName="Muted"), row, 0)
            self.values_grid.addWidget(value, row, 1)
            self.value_labels[band] = value
        self.values_grid.setColumnStretch(1, 1)


def _summary(info: RasterInfoDTO) -> str:
    """e.g. "Sentinel-2 · 2023-01-01 to 2023-12-31 · 2,783 × 2,227 px · 5 bands"."""
    dates = " to ".join(d for d in (info.start_date, info.end_date) if d)
    bands = f"{info.band_count} band{'s' if info.band_count != 1 else ''}"
    parts = (info.satellite, dates, f"{info.width:,} × {info.height:,} px", bands)
    return "  ·  ".join(part for part in parts if part)
