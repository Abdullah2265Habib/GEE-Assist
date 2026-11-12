from __future__ import annotations

from abc import ABC, abstractmethod

from backend.dto.map_dto import RasterInfoDTO


class IMapService(ABC):
    """Class diagram: IMapService. Shows downloaded GeoTIFFs: true colour, indices, classes."""

    @abstractmethod
    def describe(self, path: str) -> RasterInfoDTO:
        """What the GeoTIFF at ``path`` holds.

        Raises:
            MapError: the file is missing or is not a raster GDAL can read.
        """
