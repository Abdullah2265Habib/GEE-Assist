from __future__ import annotations

from abc import ABC, abstractmethod

from backend.dto import FormDTO


class IDataFacade(ABC):
    """Class diagram: IDataFacade. The business services' only way to reach
    external systems (Gemini, GEE) and storage (DAOs).

    Only the LLM operation exists so far; GEE (fetchChunk, validateAccess) and
    the DAO operations are added with their use cases.
    """

    @abstractmethod
    def process_query(self, prompt: str) -> FormDTO:
        """Interpret a natural-language request (delegates to IGeminiClient)."""
