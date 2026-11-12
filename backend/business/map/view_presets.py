"""The ways a GeoTIFF can be shown, from the bands it has (the first is the default)."""

from __future__ import annotations

from backend.business.map.band_roles import band_roles
from backend.dto.map_dto import RasterInfoDTO, ViewPresetDTO

CLASS_BAND = "label"  # Dynamic World's land-cover class band


def presets_for(info: RasterInfoDTO) -> list[ViewPresetDTO]:
    roles = band_roles(info.satellite, info.band_names)
    presets: list[ViewPresetDTO] = []
    if CLASS_BAND in info.band_names and info.satellite in ("Dynamic-World", ""):
        presets.append(ViewPresetDTO("classes", "Land cover classes", "classes", (CLASS_BAND,),
                                     "Each pixel's most likely land cover, in Dynamic World's colours."))
    if {"red", "green", "blue"} <= roles.keys():
        presets.append(ViewPresetDTO("true_colour", "True colour", "rgb",
                                     (roles["red"], roles["green"], roles["blue"]),
                                     "Red, green and blue bands: as the eye would see it."))
    if {"nir", "red", "green"} <= roles.keys():
        presets.append(ViewPresetDTO("false_colour", "False colour (vegetation)", "rgb",
                                     (roles["nir"], roles["red"], roles["green"]),
                                     "Near-infrared shown as red: healthy vegetation is bright red."))
    if {"nir", "red"} <= roles.keys():
        presets.append(ViewPresetDTO("ndvi", "NDVI (vegetation)", "index", (roles["nir"], roles["red"]),
                                     "(NIR - Red) / (NIR + Red): higher means denser, healthier vegetation."))
    if {"green", "nir"} <= roles.keys():
        presets.append(ViewPresetDTO("ndwi", "NDWI (water)", "index", (roles["green"], roles["nir"]),
                                     "(Green - NIR) / (Green + NIR): above 0 is usually open water."))
    for band in info.band_names:
        presets.append(ViewPresetDTO(f"band:{band}", f"Band {band}", "band", (band,),
                                     "One band on its own, on a colour scale."))
    return presets
