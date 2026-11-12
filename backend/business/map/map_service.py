"""Class diagram: MapService. Reads downloaded GeoTIFFs so they can be looked at."""

from __future__ import annotations

from pathlib import Path

from backend.business.download.naming import parse_dataset_name
from backend.business.map.i_map_service import IMapService
from backend.business.map.view_presets import presets_for
from backend.dto.map_dto import RasterInfoDTO, ViewPresetDTO
from backend.exceptions import MapError


class MapService(IMapService):
    def describe(self, path: str) -> RasterInfoDTO:
        import rasterio
        from rasterio.warp import transform_bounds

        file = Path(path)
        try:
            with rasterio.open(file) as src:
                names = tuple(name or f"Band {index}" for index, name in enumerate(src.descriptions, start=1))
                bounds = tuple(src.bounds)
                if src.crs and src.crs.to_epsg() != 4326:
                    bounds = transform_bounds(src.crs, "EPSG:4326", *bounds, densify_pts=21)
                satellite, start, end = parse_dataset_name(file.stem)
                return RasterInfoDTO(
                    path=str(file), name=file.stem, width=src.width, height=src.height, band_names=names,
                    crs=src.crs.to_string() if src.crs else "", bounds=tuple(float(v) for v in bounds),
                    nodata=src.nodata, dtype=src.dtypes[0], size_bytes=file.stat().st_size,
                    satellite=satellite, start_date=start, end_date=end,
                )
        except rasterio.errors.RasterioIOError as exc:
            raise MapError(f"Cannot open {file.name}: it is missing or not a GeoTIFF.") from exc

    def view_presets(self, info: RasterInfoDTO) -> list[ViewPresetDTO]:
        return presets_for(info)
