from __future__ import annotations

from backend.business.facade.i_business_facade import IBusinessFacade
from backend.business.request.i_request_service import IRequestService
from backend.dto import FormDTO, ValidationDTO


class BusinessFacade(IBusinessFacade):
    """Class diagram: BusinessFacade. Delegates to the services.

    Other services (user, download, analysis, map, explanation, report) are
    injected here as their use cases are implemented.
    """

    def __init__(self, request_service: IRequestService):
        self._request_service = request_service

    def submit_query(self, text: str) -> FormDTO:
        return self._request_service.submit_query(text)

    def submit_form(self, form: FormDTO) -> ValidationDTO:
        return self._request_service.validate_form(form)

    def import_aoi(self, file_path: str) -> str:
        return self._request_service.import_aoi(file_path)

    def get_kept_requests(self) -> list[FormDTO]:
        return self._request_service.get_kept_requests()
