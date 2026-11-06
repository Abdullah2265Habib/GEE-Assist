from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from backend.data.clients.i_gee_client import ProgressCallback, StopCheck
from backend.dto import ChunkDTO, FormDTO


class IDataFacade(ABC):
    """Class diagram: IDataFacade. The business services' only way to reach
    external systems (Gemini, GEE) and storage (DAOs).

    The LLM and GEE operations exist so far; the DAO operations are added with
    their use cases.
    """

    @abstractmethod
    def process_query(self, prompt: str) -> FormDTO:
        """Interpret a natural-language request (delegates to IGeminiClient)."""

    @abstractmethod
    def fetch_chunk(
        self,
        chunk: ChunkDTO,
        path: str,
        on_progress: Optional[ProgressCallback] = None,
        should_stop: Optional[StopCheck] = None,
    ) -> bool:
        """UC-05: download one chunk from GEE to ``path`` (delegates to IGEEClient)."""

    @abstractmethod
    def validate_access(self) -> bool:
        """True if Google Earth Engine can be used (delegates to IGEEClient)."""
