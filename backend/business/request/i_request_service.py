from __future__ import annotations

from abc import ABC, abstractmethod

from backend.dto import FormDTO, PlaceDTO, ValidationDTO


class IRequestService(ABC):
    """Class diagram: IRequestService.

    saveProject / listProjects come later together with persistence.
    """

    @abstractmethod
    def submit_query(self, text: str) -> FormDTO:
        """UC-02: accept a natural-language query and keep it."""

    @abstractmethod
    def validate_form(self, form: FormDTO) -> ValidationDTO:
        """UC-03: validate the form parameters; valid forms are kept."""

    @abstractmethod
    def check_form(self, form: FormDTO) -> ValidationDTO:
        """UC-03 checks only: like ``validate_form``, but the form is not kept."""

    @abstractmethod
    def import_aoi(self, file_path: str) -> str:
        """UC-04: read a GeoJSON file and return its geometry as a JSON string."""

    @abstractmethod
    def search_place(self, name: str) -> list[PlaceDTO]:
        """Find a city, region or country by name; each match carries its exact boundary as the AOI."""

    @abstractmethod
    def get_kept_requests(self) -> list[FormDTO]:
        """Requests kept so far this session (in memory until saveProject exists)."""
