import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication  # noqa: E402

from frontend.assets import EARTH_SVG  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_earth_svg_asset_exists():
    assert EARTH_SVG.suffix == ".svg" and EARTH_SVG.exists()


def test_size_follows_the_svg_viewbox(app):
    from frontend.widgets.animated_svg import AnimatedSvg

    widget = AnimatedSvg(EARTH_SVG, 400)
    assert (widget.width(), widget.height()) == (400, 300)  # viewBox 1200 x 900


def test_headless_falls_back_to_a_still_image(app):
    from frontend.widgets.animated_svg import AnimatedSvg

    widget = AnimatedSvg(EARTH_SVG, 200)
    assert widget.uses_web_engine is False
    still = widget.findChild(type(widget._view))
    assert still is not None and not still.pixmap().isNull()
