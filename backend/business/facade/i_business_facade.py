from __future__ import annotations

from abc import ABC, abstractmethod

from backend.dto import FormDTO, ValidationDTO


class IBusinessFacade(ABC):
    """Class diagram: IBusinessFacade. The only backend entry point the UI uses.

    Only the query-input operations exist so far; the rest of the diagram's
    methods (logIn, startDownload, runAnalysis, ...) are added with their use cases.
    """

    @abstractmethod
    def submit_query(self, text: str) -> FormDTO: ...

    @abstractmethod
    def submit_form(self, form: FormDTO) -> ValidationDTO: ...

    @abstractmethod
    def import_aoi(self, file_path: str) -> str: ...

    @abstractmethod
    def get_kept_requests(self) -> list[FormDTO]: ...
