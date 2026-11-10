"""What gkonsol commands can do in the app, besides calling the business facade.

The signed-in window gives the terminal three "ports":

* ``AppPort``    pages, the side bar, full screen, the theme, signing out, opening folders;
* ``PanelPort``  the terminal panel itself (maximise, height, close);
* ``FormPort``   the parameter form on the Query Input page, so ``form set ...`` fills
                 the same form the user sees.

``MemoryForm`` is a form without widgets that behaves like the real one (choosing a
dataset sets its default bands, scale, cloud cover and composite). The tests use it,
and so does the terminal when the form page is not available.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any, Callable, Optional, Protocol

from backend.config import DEFAULT_DOWNLOAD_DIR, get_dataset
from backend.dto import FormDTO, ValidationDTO

# Pages of the signed-in window, by the names commands use.
PAGES: dict[str, str] = {
    "dashboard": "Dashboard",
    "query": "Query Input",
    "downloads": "Downloads",
    "account": "Account",
}
DEFAULT_DATASET = "sentinel2_sr"
DEFAULT_CLOUD_COVER = 20


class AppPort(Protocol):
    def current_page(self) -> str: ...
    def show_page(self, page: str) -> None: ...
    def sign_out(self) -> None: ...
    def is_side_bar_expanded(self) -> bool: ...
    def set_side_bar_expanded(self, expanded: bool) -> None: ...
    def is_full_screen(self) -> bool: ...
    def set_full_screen(self, on: bool) -> None: ...
    def restart_with_theme(self, theme: str) -> None: ...
    def open_path(self, path: str) -> bool: ...
    def open_url(self, url: str) -> bool: ...
    def open_user_admin(self) -> None: ...
    def quit(self) -> None: ...


class PanelPort(Protocol):
    def is_terminal_maximized(self) -> bool: ...
    def set_terminal_maximized(self, on: bool) -> None: ...
    def terminal_height(self) -> int: ...
    def set_terminal_height(self, pixels: int) -> None: ...
    def hide_terminal(self) -> None: ...


class FormPort(Protocol):
    def current(self) -> FormDTO: ...
    def reset(self) -> None: ...
    def set_dataset(self, key: str) -> None: ...
    def set_bands(self, bands: list[str]) -> None: ...
    def set_scale(self, metres: int) -> None: ...
    def set_cloud_cover(self, percent: int) -> None: ...
    def set_composite(self, method: str) -> None: ...
    def set_dates(self, start: date, end: date) -> None: ...
    def set_area(self, geojson: str, name: str, from_file: bool = False) -> None: ...
    def clear_area(self) -> None: ...
    def set_crs(self, code: str) -> None: ...
    def set_output_dir(self, folder: str) -> None: ...
    def set_analysis(self, analysis_type: str, processes: list[str]) -> None: ...
    def apply(self, form: FormDTO) -> list[str]: ...
    def submit(self) -> ValidationDTO: ...


def months_before(day: date, months: int) -> date:
    """The same day ``months`` earlier (the month's last day if it is shorter), like QDate.addMonths."""
    month, year = day.month - months, day.year
    while month < 1:
        month, year = month + 12, year - 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


class MemoryForm:
    """The parameter form without widgets. ``submit`` validates and keeps it, like the real form."""

    def __init__(self, facade: Any, today: Callable[[], date] = date.today):
        self._facade = facade
        self._today = today
        self._form = FormDTO()
        self.reset()

    def current(self) -> FormDTO:
        return replace(self._form, bands=list(self._form.bands), processes=list(self._form.processes))

    def reset(self) -> None:
        end = self._today()
        self._form = FormDTO(start_date=months_before(end, 3), end_date=end, crs="EPSG:4326",
                             output_dir=str(DEFAULT_DOWNLOAD_DIR))
        self.set_dataset(DEFAULT_DATASET)

    def set_dataset(self, key: str) -> None:
        info = get_dataset(key)
        if info is None:
            raise ValueError(f"Unknown dataset {key!r}")
        form = self._form
        form.dataset = key
        form.bands = list(info.default_bands)
        form.scale = info.default_scale
        form.max_cloud_cover = DEFAULT_CLOUD_COVER if info.supports_cloud_filter else None
        form.composite = info.default_composite
        # The date pickers only offer the dataset's dates.
        lowest, highest = info.min_date, info.max_date or self._today()
        form.start_date = min(max(form.start_date or lowest, lowest), highest)
        form.end_date = min(max(form.end_date or highest, lowest), highest)
        if form.start_date >= form.end_date:
            form.start_date = max(lowest, months_before(form.end_date, 3))
        # Analyses the dataset cannot do are dropped.
        supported = info.supported_analyses.get(form.analysis_type, ())
        if form.analysis_type and not supported:
            form.analysis_type, form.processes = "", []
        else:
            form.processes = [process for process in form.processes if process in supported]

    def set_bands(self, bands: list[str]) -> None:
        self._form.bands = list(bands)

    def set_scale(self, metres: int) -> None:
        self._form.scale = metres

    def set_cloud_cover(self, percent: int) -> None:
        self._form.max_cloud_cover = percent

    def set_composite(self, method: str) -> None:
        self._form.composite = method

    def set_dates(self, start: date, end: date) -> None:
        self._form.start_date, self._form.end_date = start, end

    def set_area(self, geojson: str, name: str, from_file: bool = False) -> None:
        self._form.aoi, self._form.aoi_name = geojson, name

    def clear_area(self) -> None:
        self._form.aoi, self._form.aoi_name = "", ""

    def set_crs(self, code: str) -> None:
        self._form.crs = code

    def set_output_dir(self, folder: str) -> None:
        self._form.output_dir = folder

    def set_analysis(self, analysis_type: str, processes: list[str]) -> None:
        self._form.analysis_type = analysis_type
        self._form.processes = list(processes) if analysis_type else []

    def apply(self, form: FormDTO) -> list[str]:
        """Fill in what ``form`` has (Gemini's reading of a request); returns the parts filled."""
        filled: list[str] = []
        info = get_dataset(form.dataset) if form.dataset else None
        if info is not None:
            self.set_dataset(form.dataset)
            filled.append("dataset")
            if form.bands:
                self.set_bands(form.bands)
                filled.append("bands")
            if form.scale:
                self.set_scale(form.scale)
            if form.max_cloud_cover is not None and info.supports_cloud_filter:
                self.set_cloud_cover(form.max_cloud_cover)
                filled.append("cloud cover")
            if form.composite:
                self.set_composite(form.composite)
        if form.start_date or form.end_date:
            self.set_dates(form.start_date or self._form.start_date, form.end_date or self._form.end_date)
            filled.append("dates")
        if form.aoi:
            name = form.aoi_name or "Area from your request"
            self.set_area(form.aoi, name)
            filled.append(f"area ({name})")
        supported = get_dataset(self._form.dataset).supported_analyses
        if form.analysis_type and form.analysis_type in supported:
            self.set_analysis(form.analysis_type, form.processes)
            filled.append("analysis")
        return filled

    def submit(self) -> ValidationDTO:
        return self._facade.submit_form(self.current())


@dataclass
class Context:
    """What a command gets besides its arguments."""

    facade: Any                 # IBusinessFacade
    out: Any                    # output.Writer
    app: AppPort
    form: FormPort
    panel: PanelPort
    shell: Any = None           # the Shell running the command (help, history, the registry)
    extra: dict[str, Any] = field(default_factory=dict)  # state commands keep between runs

    @property
    def user(self) -> Optional[Any]:
        return self.facade.get_current_user()

    @property
    def is_admin(self) -> bool:
        user = self.user
        return bool(user is not None and getattr(user, "is_admin", False))
