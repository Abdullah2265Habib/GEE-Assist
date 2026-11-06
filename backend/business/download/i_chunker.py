from __future__ import annotations

from abc import ABC, abstractmethod

from backend.dto import ChunkDTO, FormDTO


class IChunker(ABC):
    """Class diagram: IChunker."""

    @abstractmethod
    def split(self, form: FormDTO) -> list[ChunkDTO]:
        """Cut the requested raster into chunks no larger than the configured chunk size.

        Chunks are returned top strip first and together cover the whole output grid.
        """
