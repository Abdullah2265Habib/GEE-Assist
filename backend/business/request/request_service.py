from __future__ import annotations

from backend.business.request.i_request_service import IRequestService
from backend.dto import FormDTO, ValidationDTO
from backend.config.limits import MAX_QUERY_LENGTH
from backend.exceptions import ValidationError


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
        """Validate and keep the query. Returns a FormDTO holding only the query
        text; Interpret Query (LLM) fills in the parameters at the next stage.

        Raises:
            ValidationError: the query is empty (5a) or too long.
        """
        query = " ".join((text or "").split())
        if not query:
            raise ValidationError("Please enter a request describing the data or analysis you need.")
        if len(query) > MAX_QUERY_LENGTH:
            raise ValidationError(f"The query is too long ({len(query)} characters, limit {MAX_QUERY_LENGTH}).")

        form = FormDTO(source="nl", query_text=query)
        self._keep(form)
        return form

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
