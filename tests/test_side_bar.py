"""The sliding side bar (no window on screen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtGui import QPixmap  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

from frontend.widgets.side_bar import (  # noqa: E402
    BUTTON_HEIGHT,
    COLLAPSED_WIDTH,
    EXPANDED_WIDTH,
    SIDE_MARGIN,
    SLIDE_MS,
    SideBar,
)


class CompactLabel(QLabel):
    def __init__(self):
        super().__init__("Ayesha Khan")
        self.compact = None

    def set_compact(self, compact: bool) -> None:
        self.compact = compact


def _wait_for_slide(bar, timeout_ms: int = 3000) -> None:
    """Wait until the slide has finished (slower when the whole test suite is running)."""
    waited = 0
    while bar.is_sliding() and waited < timeout_ms:
        QTest.qWait(10)
        waited += 10


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def bar(app):
    side = SideBar(QPixmap(48, 48))
    yield side
    side.deleteLater()


def test_starts_collapsed_with_short_labels(bar):
    downloads = bar.add_button("Downloads", "D")
    assert not bar.is_expanded() and bar.width() == COLLAPSED_WIDTH
    assert downloads.text() == "D"
    assert bar.logo.toolTip() == "Expand the side bar"


def test_can_start_expanded_with_full_names(app):
    bar = SideBar(QPixmap(48, 48), expanded=True)
    downloads = bar.add_button("Downloads", "D")
    assert bar.is_expanded() and bar.width() == EXPANDED_WIDTH
    assert downloads.text() == "Downloads"
    assert bar.logo.toolTip() == "Collapse the side bar"
    bar.deleteLater()


def test_collapsed_shows_short_labels(bar):
    downloads = bar.add_button("Downloads", "D")
    footer = CompactLabel()
    bar.add_widget(footer, footer=True)

    bar.set_expanded(False, animate=False)
    assert bar.width() == COLLAPSED_WIDTH
    assert downloads.text() == "D" and downloads.toolTip() == "Downloads"
    assert footer.compact is True
    assert bar.logo.toolTip() == "Expand the side bar"

    bar.set_expanded(True, animate=False)
    assert downloads.text() == "Downloads" and footer.compact is False


def test_widgets_added_while_collapsed_start_compact(bar):
    bar.set_expanded(False, animate=False)
    assert bar.add_button("Sign out", "S").text() == "S"


def test_clicking_the_logo_slides_the_bar_open_and_closed(bar):
    downloads = bar.add_button("Downloads", "D")
    bar.show()
    changes = []
    bar.expanded_changed.connect(changes.append)

    bar.logo.click()
    assert bar.is_sliding() and bar.is_expanded()
    assert downloads.text() == "Downloads"   # uncovered as the bar widens
    _wait_for_slide(bar)
    assert not bar.is_sliding() and bar.width() == EXPANDED_WIDTH

    bar.logo.click()
    assert downloads.text() == "Downloads"   # covered as the bar narrows, switched at the end
    _wait_for_slide(bar)
    assert bar.width() == COLLAPSED_WIDTH and downloads.text() == "D"
    assert changes == [True, False]


def test_reversing_mid_slide_ends_at_the_new_width(bar):
    downloads = bar.add_button("Downloads", "D")
    bar.show()
    bar.logo.click()                          # start opening
    QTest.qWait(SLIDE_MS // 3)
    bar.logo.click()                          # close again before it finished
    _wait_for_slide(bar)
    assert not bar.is_expanded() and bar.width() == COLLAPSED_WIDTH and downloads.text() == "D"


def test_footer_buttons_sit_below_the_navigation(bar):
    downloads = bar.add_button("Downloads", "D")
    sign_out = bar.add_button("Sign out", "S", footer=True)
    bar.show()
    assert sign_out.y() > downloads.y() + downloads.height()


def test_logo_stays_on_the_left_expanded_and_collapsed(bar):
    bar.show()
    assert bar.logo.x() == SIDE_MARGIN
    bar.set_expanded(False, animate=False)
    QApplication.processEvents()
    assert bar.logo.x() == SIDE_MARGIN
    assert bar.logo.x() + bar.logo.width() <= COLLAPSED_WIDTH  # fits the collapsed bar


def test_collapsed_buttons_are_circles_under_the_logo(bar):
    downloads = bar.add_button("Downloads", "D")
    bar.show()
    bar.set_expanded(False, animate=False)
    QApplication.processEvents()

    assert downloads.width() == downloads.height() == BUTTON_HEIGHT
    assert downloads.property("compact") is True  # styled with a radius of half its size
    assert downloads.geometry().center().x() == bar.logo.geometry().center().x()

    bar.set_expanded(True, animate=False)
    QApplication.processEvents()
    assert downloads.width() > BUTTON_HEIGHT  # the full name fills the row again


def test_buttons_added_while_collapsed_are_circles_too(bar):
    bar.show()
    bar.set_expanded(False, animate=False)
    later = bar.add_button("Downloads", "D")
    QApplication.processEvents()
    assert later.width() == BUTTON_HEIGHT


def _in_bar(bar, widget):
    """``widget``'s rectangle in the side bar's coordinates."""
    rect = widget.rect()
    rect.moveTopLeft(widget.mapTo(bar, rect.topLeft()))
    return rect


def test_back_button_is_a_circle_centred_above_the_logo(bar):
    bar.show()
    QApplication.processEvents()
    back, logo = _in_bar(bar, bar.back_button), bar.logo.geometry()

    assert back.width() == back.height() == BUTTON_HEIGHT
    assert back.bottom() < logo.top()
    assert abs(back.center().x() - logo.center().x()) <= 1


def test_home_icon_takes_the_back_buttons_place(bar):
    bar.show()
    QApplication.processEvents()
    back, logo_top = _in_bar(bar, bar.back_button), bar.logo.y()

    bar.show_back(False)
    QApplication.processEvents()
    assert bar.back_button.isHidden() and not bar.home_icon.isHidden()
    assert _in_bar(bar, bar.home_icon) == back      # the same spot
    assert bar.logo.y() == logo_top                 # the logo does not move

    bar.show_back(True)
    assert not bar.back_button.isHidden() and bar.home_icon.isHidden()
