"""Which band of a download is blue, green, red, near-infrared or short-wave infrared.

Band names alone are not enough: Landsat 8/9 and Landsat 5/7 use the same names for
different colours (``SR_B2`` is blue on Landsat 8, green on Landsat 5). So the
satellite in the download's name decides; for a file from elsewhere, Sentinel-2 and
MODIS band names are recognised on their own.
"""

from __future__ import annotations

ROLES = ("blue", "green", "red", "nir", "swir1")

_SENTINEL_2 = {"blue": "B2", "green": "B3", "red": "B4", "nir": "B8", "swir1": "B11"}
_LANDSAT_8_9 = {"blue": "SR_B2", "green": "SR_B3", "red": "SR_B4", "nir": "SR_B5", "swir1": "SR_B6"}
_LANDSAT_5_7 = {"blue": "SR_B1", "green": "SR_B2", "red": "SR_B3", "nir": "SR_B4", "swir1": "SR_B5"}
_MODIS = {"blue": "sur_refl_b03", "green": "sur_refl_b04", "red": "sur_refl_b01", "nir": "sur_refl_b02",
          "swir1": "sur_refl_b06"}

_BY_SATELLITE = {
    "Sentinel-2": _SENTINEL_2,
    "Landsat-8": _LANDSAT_8_9,
    "Landsat-9": _LANDSAT_8_9,
    "Landsat-5": _LANDSAT_5_7,
    "Landsat-7": _LANDSAT_5_7,
    "MODIS-Terra": _MODIS,
}


def band_roles(satellite: str, band_names: tuple[str, ...]) -> dict[str, str]:
    """Role (``"red"``, ``"nir"``, ...) -> band name, for the roles this file has."""
    table = _BY_SATELLITE.get(satellite) or _guess_table(band_names)
    if not table:
        return {}
    present = set(band_names)
    return {role: band for role, band in table.items() if band in present}


def _guess_table(band_names: tuple[str, ...]) -> dict[str, str]:
    names = set(band_names)
    if {"B2", "B3", "B4"} <= names:
        return _SENTINEL_2
    if any(name.startswith("sur_refl_b") for name in names):
        return _MODIS
    return {}  # e.g. Landsat without its satellite: the names are ambiguous
