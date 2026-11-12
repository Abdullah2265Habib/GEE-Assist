from __future__ import annotations

from abc import ABC, abstractmethod

from backend.dto.map_dto import RasterInfoDTO, RasterViewDTO, ViewPresetDTO


class IMapService(ABC):
    """Class diagram: IMapService. Shows downloaded GeoTIFFs: true colour, indices, classes."""

    @abstractmethod
    def describe(self, path: str) -> RasterInfoDTO:
        """What the GeoTIFF at ``path`` holds.

        Raises:
            MapError: the file is missing or is not a raster GDAL can read.
        """

    @abstractmethod
    def view_presets(self, info: RasterInfoDTO) -> list[ViewPresetDTO]:
        """The ways the file can be shown (true colour, NDVI, ...), the default first."""

    @abstractmethod
    def render(self, info: RasterInfoDTO, preset: ViewPresetDTO, max_size: int = 1600) -> RasterViewDTO:
        """A preview of the file drawn for ``preset``, at most ``max_size`` pixels on its longer side.

        Raises:
            MapError: the file cannot be read or lacks a band the preset needs.
        """

    @abstractmethod
    def values_at(self, info: RasterInfoDTO, lon: float, lat: float) -> dict[str, float | None]:
        """Each band's value at a point, read from the full-resolution file.

        A band has ``None`` where it has no data, and every band does outside the image.
        """
