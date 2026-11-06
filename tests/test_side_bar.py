"""The sliding side bar (no window on screen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtGui import QPixmap  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

from frontend.widgets.side_bar import COLLAPSED_WIDTH, EXPANDED_WIDTH, SLIDE_MS, SideBar  # noqa: E402


class CompactLabel(QLabel):
    def __init__(self):
        super().__init__("Ayesha Khan")
        self.compact = None

    def set_compact(self, compact: bool) -> None:
        self.compact = compact


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def bar(app):
    side = SideBar(QPixmap(48, 48))
    yield side
    side.deleteLater()


def test_starts_expanded_with_full_names(bar):
    downloads = bar.add_button("Downloads", "D")
    assert bar.is_expanded() and bar.width() == EXPANDED_WIDTH
    assert downloads.text() == "Downloads"
    assert bar.logo.toolTip() == "Collapse the side bar"


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


def test_clicking_the_logo_slides_the_bar_closed_and_open(bar):
    downloads = bar.add_button("Downloads", "D")
    bar.show()
    changes = []
    bar.expanded_changed.connect(changes.append)

    bar.logo.click()
    assert bar.is_sliding() and not bar.is_expanded()
    assert downloads.text() == "Downloads"   # covered as the bar narrows, switched at the end
    QTest.qWait(SLIDE_MS + 150)
    assert not bar.is_sliding() and bar.width() == COLLAPSED_WIDTH and downloads.text() == "D"

    bar.logo.click()
    assert downloads.text() == "Downloads"   # uncovered as the bar widens
    QTest.qWait(SLIDE_MS + 150)
    assert bar.width() == EXPANDED_WIDTH
    assert changes == [False, True]


def test_reversing_mid_slide_ends_at_the_new_width(bar):
    downloads = bar.add_button("Downloads", "D")
    bar.show()
    bar.logo.click()                          # start closing
    QTest.qWait(SLIDE_MS // 3)
    bar.logo.click()                          # open again before it finished
    QTest.qWait(SLIDE_MS + 150)
    assert bar.is_expanded() and bar.width() == EXPANDED_WIDTH and downloads.text() == "Downloads"
