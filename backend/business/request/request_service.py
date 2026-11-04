from __future__ import annotations

from backend.business.request.i_request_service import IRequestService
from backend.dto import FormDTO, ValidationDTO


class RequestService(IRequestService):
    """Class diagram: RequestService (-dataFacade: IDataFacade).

    The data facade is optional for now: keeping input only needs memory.
    It will be used for Interpret Query (Gemini) and saveProject (MongoDB).
    """

    def __init__(self, data_facade=None):
        self._data_facade = data_facade
        self._kept_requests: list[FormDTO] = []

    # ------------------------------------------------------------------
    # UC-02 Enter Natural Language Query      (branch: query-input-nl)
    # ------------------------------------------------------------------
    def submit_query(self, text: str) -> FormDTO:
        raise NotImplementedError("Natural-language input is built on branch query-input-nl.")

    # ------------------------------------------------------------------
    # UC-03 Fill Parameter Form               (branch: query-input-form)
    # ------------------------------------------------------------------
    def validate_form(self, form: FormDTO) -> ValidationDTO:
        raise NotImplementedError("Parameter form is built on branch query-input-form.")

    # ------------------------------------------------------------------
    # UC-04 Import GeoJSON                    (branch: query-input-form)
    # ------------------------------------------------------------------
    def import_aoi(self, file_path: str) -> str:
        raise NotImplementedError("GeoJSON import is built on branch query-input-form.")

    # ------------------------------------------------------------------
    # Keeping the data
    # ------------------------------------------------------------------
    def get_kept_requests(self) -> list[FormDTO]:
        return list(self._kept_requests)

    def _keep(self, form: FormDTO) -> None:
        self._kept_requests.append(form)
