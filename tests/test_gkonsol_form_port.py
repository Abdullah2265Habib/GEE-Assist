"""gkonsol's form commands fill the real parameter form (its web map replaced; no window on screen)."""

import json
import os
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication  # noqa: E402

from backend.business.request import RequestService  # noqa: E402
from frontend.gkonsol.commands import build_registry  # noqa: E402
from frontend.gkonsol.form_port import WidgetForm  # noqa: E402
from frontend.gkonsol.history import History  # noqa: E402
from frontend.gkonsol.output import BufferSink  # noqa: E402
from frontend.gkonsol.shell import Shell  # noqa: E402
from frontend.views import parameter_form_view  # noqa: E402
from frontend.views.parameter_form_view import ParameterFormView  # noqa: E402
from tests.gkonsol_fakes import FakeApp, FakePanel, StepScheduler, facade  # noqa: E402
from tests.test_parameter_form_api import SQUARE, StubMap  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def setup(app, monkeypatch, tmp_path):
    monkeypatch.setattr(parameter_form_view, "AoiMapWidget", StubMap)
    fake = facade()
    service = RequestService()
    for name, method in (("submit_form", service.validate_form), ("check_form", service.check_form),
                         ("get_kept_requests", service.get_kept_requests), ("import_aoi", service.import_aoi)):
        getattr(fake, name).side_effect = method
    view = ParameterFormView(fake)
    view.set_output_dir(str(tmp_path))
    sink, scheduler = BufferSink(), StepScheduler()
    shell = Shell(build_registry(), fake, FakeApp(), WidgetForm(view), FakePanel(), sink, scheduler, History())

    def run(line):
        before = len(sink.lines)
        shell.submit(line)
        scheduler.settle()
        return "\n".join(sink.text().split("\n")[before:])

    yield view, run, fake
    view.deleteLater()


def test_what_is_typed_shows_in_the_form(setup):
    view, run, _ = setup
    run("form set dataset landsat8_l2")
    run("form set bands SR_B4 SR_B5")
    run("form set dates 2024-06-01 2024-08-31")
    run("form aoi bbox 73 31 73.1 31.1")
    run("form set analysis Vegetation NDVI")
    assert view.dataset_combo.currentData() == "landsat8_l2"
    assert view.bands_combo.checked() == ["SR_B4", "SR_B5"]
    assert view.start_date_edit.date().toPyDate() == date(2024, 6, 1)
    assert view.aoi_draw_toggle.isChecked() and view.analysis_combo.currentData() == "Vegetation"


def test_what_is_entered_in_the_form_shows_in_form_show(setup):
    view, run, _ = setup
    view.set_dataset("modis_lst")
    assert "modis_lst" in run("form show")


def test_submitting_from_the_terminal_keeps_the_request_in_the_form(setup):
    view, run, fake = setup
    kept = []
    view.request_kept.connect(kept.append)
    assert "Area: Specify an Area of Interest" in run("form submit")
    assert not view._error_labels["aoi"].isHidden()  # the form shows the error as well
    run("form aoi bbox 73 31 73.1 31.1")
    assert "kept as request #1" in run("form submit") and len(kept) == 1


def test_a_geojson_file_switches_the_form_to_file_mode(setup, tmp_path):
    view, run, _ = setup
    path = tmp_path / "area.geojson"
    path.write_text(json.dumps(SQUARE), encoding="utf-8")
    run(f'form aoi file "{path}"')
    assert view.aoi_file_toggle.isChecked() and "area.geojson" in view.aoi_file_label.text()


def test_reset_from_the_terminal(setup):
    view, run, _ = setup
    run("form set scale 99")
    run("form reset -y")
    assert view.scale_spin.value() == 10
