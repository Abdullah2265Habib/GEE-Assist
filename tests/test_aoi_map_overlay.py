"""Laying a GeoTIFF preview over the AOI map (the JavaScript the widget sends)."""

import base64
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt6")

from frontend.widgets.aoi_map_widget import MAP_HTML, AoiMapWidget  # noqa: E402


def _sent(method, *args, **kwargs):
    """The scripts ``method`` would run in the map page."""
    scripts = []
    method(SimpleNamespace(_run=scripts.append), *args, **kwargs)
    return scripts


def test_show_image_sends_the_png_its_area_and_title():
    png = b"\x89PNG fake image"
    [script] = _sent(AoiMapWidget.show_image, png, (73.0, 31.0, 73.2, 31.1), "Sentinel-2 · NDVI", opacity=0.6)

    match = re.fullmatch(r'showImage\((".*?"), 73\.0, 31\.0, 73\.2, 31\.1, (".*?"), 0\.6\)', script)
    assert match
    url, title = json.loads(match.group(1)), json.loads(match.group(2))
    assert url == "data:image/png;base64," + base64.b64encode(png).decode()
    assert title == "Sentinel-2 · NDVI"


def test_clear_image_removes_it():
    assert _sent(AoiMapWidget.clear_image) == ["clearImage()"]


def test_the_map_page_defines_the_overlay_functions():
    page = Path(MAP_HTML).read_text(encoding="utf-8")
    for name in ("function showImage(", "function clearImage(", "L.imageOverlay(", "Remove from map"):
        assert name in page
