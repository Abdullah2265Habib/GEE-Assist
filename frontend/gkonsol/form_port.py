"""gkonsol's form port over the parameter form on the Query Input page.

``form set ...`` and the other form commands fill this form, so what is typed in the
terminal shows in the form, and what is entered in the form shows in ``form show``.
"""

from __future__ import annotations

from datetime import date

from backend.dto import FormDTO, ValidationDTO
from frontend.views.parameter_form_view import ParameterFormView


class WidgetForm:
    def __init__(self, view: ParameterFormView):
        self._view = view

    def current(self) -> FormDTO:
        return self._view.collect_form()

    def reset(self) -> None:
        self._view.reset()

    def set_dataset(self, key: str) -> None:
        self._view.set_dataset(key)

    def set_bands(self, bands: list[str]) -> None:
        self._view.set_bands(bands)

    def set_scale(self, metres: int) -> None:
        self._view.set_scale(metres)

    def set_cloud_cover(self, percent: int) -> None:
        self._view.set_cloud_cover(percent)

    def set_composite(self, method: str) -> None:
        self._view.set_composite(method)

    def set_dates(self, start: date, end: date) -> None:
        self._view.set_dates(start, end)

    def set_area(self, geojson: str, name: str, from_file: bool = False) -> None:
        if from_file:
            self._view.set_imported_area(geojson, name)
        else:
            self._view.set_drawn_area(geojson, name)

    def clear_area(self) -> None:
        self._view.clear_area()

    def set_crs(self, code: str) -> None:
        self._view.set_crs(code)

    def set_output_dir(self, folder: str) -> None:
        self._view.set_output_dir(folder)

    def set_analysis(self, analysis_type: str, processes: list[str]) -> None:
        self._view.set_analysis(analysis_type, processes)

    def apply(self, form: FormDTO) -> list[str]:
        return self._view.apply_form(form)

    def submit(self) -> ValidationDTO:
        return self._view.submit()
