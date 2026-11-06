from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

from backend.dto import ChunkDTO

# Called after each GEE request with (raster bytes written, as float32, bytes received from GEE).
# The first drives the progress bar; the second is what the network actually carried.
ProgressCallback = Callable[[int, int], None]
StopCheck = Callable[[], bool]             # True when the download is paused or cancelled


class IGEEClient(ABC):
    """Class diagram: IGEEClient. Gateway to Google Earth Engine."""

    @abstractmethod
    def fetch_chunk(
        self,
        chunk: ChunkDTO,
        path: str,
        on_progress: Optional[ProgressCallback] = None,
        should_stop: Optional[StopCheck] = None,
    ) -> bool:
        """Download ``chunk`` from GEE and write it to ``path`` as a GeoTIFF.

        Returns True once the chunk is complete, or False if ``should_stop`` asked it
        to stop first; calling it again with the same path continues where it stopped.

        Raises:
            GEEError: GEE is not set up, refused the request, or has no images for it.
        """

    @abstractmethod
    def validate_access(self) -> bool:
        """True if Earth Engine is signed in and the configured project can be used."""
