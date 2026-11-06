from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from backend.dto import ChunkDTO, DatasetDTO


class IChunkMerger(ABC):
    """Class diagram: IChunkMerger."""

    @abstractmethod
    def merge(self, chunks: list[ChunkDTO], output_path: Optional[str] = None) -> DatasetDTO:
        """Join downloaded chunks (vertically adjacent strips, top first) into one GeoTIFF.

        ``output_path`` defaults to a file next to the first chunk. The input files are
        left in place; the caller decides when to delete them.
        """
