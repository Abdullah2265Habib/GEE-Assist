from __future__ import annotations

from backend.data.clients.i_gemini_client import IGeminiClient
from backend.data.i_data_facade import IDataFacade
from backend.dto import FormDTO


class DataFacade(IDataFacade):
    """Class diagram: DataFacade (-geminiClient, -geeClient, -userDAO, -projectDAO, -formulaDAO).

    The GEE client and DAOs are wired in when downloading and persistence are built.
    """

    def __init__(self, gemini_client: IGeminiClient, gee_client=None, user_dao=None, project_dao=None, formula_dao=None):
        self._gemini_client = gemini_client
        self._gee_client = gee_client
        self._user_dao = user_dao
        self._project_dao = project_dao
        self._formula_dao = formula_dao

    def process_query(self, prompt: str) -> FormDTO:
        return self._gemini_client.process_query(prompt)
