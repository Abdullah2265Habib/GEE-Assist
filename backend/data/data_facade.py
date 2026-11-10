from __future__ import annotations

from typing import Optional

from backend.data.clients.i_gee_client import IGEEClient, ProgressCallback, StopCheck
from backend.data.clients.i_gemini_client import IGeminiClient
from backend.data.i_data_facade import IDataFacade
from backend.dto import CheckDTO, ChunkDTO, FormDTO
from backend.dto.check_dto import CHECK_FAIL
from backend.exceptions import GEEError

_NO_GEE = "Google Earth Engine is not set up in this build."


class DataFacade(IDataFacade):
    """Class diagram: DataFacade (-geminiClient, -geeClient, -userDAO, -projectDAO, -formulaDAO).

    The DAOs are wired in when persistence is built.
    """

    def __init__(
        self,
        gemini_client: IGeminiClient,
        gee_client: Optional[IGEEClient] = None,
        user_dao=None,
        project_dao=None,
        formula_dao=None,
    ):
        self._gemini_client = gemini_client
        self._gee_client = gee_client
        self._user_dao = user_dao
        self._project_dao = project_dao
        self._formula_dao = formula_dao

    def process_query(self, prompt: str) -> FormDTO:
        return self._gemini_client.process_query(prompt)

    def fetch_chunk(
        self,
        chunk: ChunkDTO,
        path: str,
        on_progress: Optional[ProgressCallback] = None,
        should_stop: Optional[StopCheck] = None,
    ) -> bool:
        return self._gee().fetch_chunk(chunk, path, on_progress, should_stop)

    def validate_access(self) -> bool:
        return self._gee_client is not None and self._gee_client.validate_access()

    def diagnose_gee(self) -> list[CheckDTO]:
        if self._gee_client is None:
            return [CheckDTO("Earth Engine", CHECK_FAIL, _NO_GEE)]
        return self._gee_client.diagnose()

    def begin_gee_sign_in(self) -> str:
        return self._gee().begin_sign_in()

    def complete_gee_sign_in(self, should_stop: Optional[StopCheck] = None) -> str:
        return self._gee().complete_sign_in(should_stop)

    def cancel_gee_sign_in(self) -> None:
        if self._gee_client is not None:
            self._gee_client.cancel_sign_in()

    def _gee(self) -> IGEEClient:
        if self._gee_client is None:
            raise GEEError(_NO_GEE)
        return self._gee_client
