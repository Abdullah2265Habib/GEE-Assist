from __future__ import annotations

from abc import ABC, abstractmethod

from backend.dto import PlaceDTO


class IGeocodingClient(ABC):
    """Gateway to a place-search service: turns a place name into its boundary."""

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> list[PlaceDTO]:
        """Places matching ``query`` (best match first), each with its GeoJSON outline.

        A place without a known boundary comes back with a non-polygon geometry
        (e.g. a Point); RequestService leaves such places out.

        Raises:
            PlaceSearchError: the service could not be reached or refused the request.
        """
