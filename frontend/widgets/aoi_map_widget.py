"""Interactive map for picking the Area of Interest.

* bbox mode: the user draws a rectangle (Leaflet.draw); its bounds are
  emitted through ``bbox_drawn``. Python can also push a bbox onto the map.
* file mode: shows the outline of an imported GeoJSON AOI.

Requires PyQt6-WebEngine. Without it the widget shows a notice and the form
falls back to manual coordinate entry.
"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QFile, QIODevice, QObject, Qt, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

try:
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWebEngineCore import QWebEngineScript, QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    WEB_ENGINE_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on installed packages
    WEB_ENGINE_AVAILABLE = False

MAP_HTML = Path(__file__).resolve().parents[1] / "resources" / "aoi_map.html"


class _MapBridge(QObject):
    """Object exposed to JavaScript as ``bridge``."""

    ready = pyqtSignal()
    bbox_drawn = pyqtSignal(float, float, float, float)
    bbox_cleared = pyqtSignal()

    @pyqtSlot()
    def mapReady(self) -> None:  # noqa: N802 (called from JS)
        self.ready.emit()

    @pyqtSlot(float, float, float, float)
    def bboxDrawn(self, west: float, south: float, east: float, north: float) -> None:  # noqa: N802
        self.bbox_drawn.emit(west, south, east, north)

    @pyqtSlot()
    def bboxCleared(self) -> None:  # noqa: N802
        self.bbox_cleared.emit()


class AoiMapWidget(QWidget):
    bbox_drawn = pyqtSignal(float, float, float, float)  # min_lon, min_lat, max_lon, max_lat
    bbox_cleared = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ready = False
        self._pending: list[str] = []
        self._view = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not WEB_ENGINE_AVAILABLE:
            notice = QLabel("Map unavailable: install PyQt6-WebEngine. Enter coordinates manually below.")
            notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
            notice.setWordWrap(True)
            layout.addWidget(notice)
            return

        self._bridge = _MapBridge(self)
        self._bridge.ready.connect(self._on_ready)
        self._bridge.bbox_drawn.connect(self.bbox_drawn)
        self._bridge.bbox_cleared.connect(self.bbox_cleared)

        self._channel = QWebChannel(self)
        self._channel.registerObject("bridge", self._bridge)

        self._view = QWebEngineView(self)
        self._view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self._inject_webchannel_script()
        self._view.page().setWebChannel(self._channel)
        self._view.load(QUrl.fromLocalFile(str(MAP_HTML)))
        layout.addWidget(self._view)

    # ------------------------------------------------------------- public API
    @property
    def available(self) -> bool:
        return self._view is not None

    def set_mode(self, mode: str) -> None:
        """``"bbox"`` (draw rectangle) or ``"file"`` (show imported GeoJSON)."""
        self._run(f"setMode({json.dumps(mode)})")

    def set_bbox(self, min_lon: float, min_lat: float, max_lon: float, max_lat: float, fit: bool = True) -> None:
        self._run(f"setBbox({min_lon}, {min_lat}, {max_lon}, {max_lat}, {'true' if fit else 'false'})")

    def clear_bbox(self) -> None:
        self._run("clearBbox()")

    def show_geojson(self, geojson: str) -> None:
        self._run(f"showGeoJSON({json.dumps(geojson)})")

    # --------------------------------------------------------------- internals
    def _inject_webchannel_script(self) -> None:
        """Inject Qt's qwebchannel.js before the page's own scripts run."""
        source = QFile(":/qtwebchannel/qwebchannel.js")
        if not source.open(QIODevice.OpenModeFlag.ReadOnly):
            return
        script = QWebEngineScript()
        script.setName("qwebchannel")
        script.setSourceCode(bytes(source.readAll()).decode("utf-8"))
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        self._view.page().scripts().insert(script)
        source.close()

    def _run(self, script: str) -> None:
        if self._view is None:
            return
        if self._ready:
            self._view.page().runJavaScript(script)
        else:
            self._pending.append(script)

    def _on_ready(self) -> None:
        self._ready = True
        for script in self._pending:
            self._view.page().runJavaScript(script)
        self._pending.clear()
