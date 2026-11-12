"""MapService: reading downloaded GeoTIFFs so they can be shown."""

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin  # noqa: E402

from backend.business.map import MapService  # noqa: E402
from backend.exceptions import MapError  # noqa: E402

NODATA = -9999.0


def write_tif(path, bands: dict, crs="EPSG:4326", origin=(73.0, 31.1), pixel=0.001):
    """A small float32 GeoTIFF with one band per entry of ``bands`` (name -> 2-D array)."""
    arrays = list(bands.values())
    height, width = arrays[0].shape
    with rasterio.open(path, "w", driver="GTiff", width=width, height=height, count=len(arrays), dtype="float32",
                       crs=crs, transform=from_origin(origin[0], origin[1], pixel, pixel), nodata=NODATA) as dst:
        for index, (name, data) in enumerate(bands.items(), start=1):
            dst.write(data.astype("float32"), index)
            dst.set_band_description(index, name)
    return path


@pytest.fixture
def sentinel_tif(tmp_path):
    shape = (40, 50)
    bands = {name: np.full(shape, value, dtype="float32")
             for name, value in (("B2", 500), ("B3", 800), ("B4", 600), ("B8", 3000), ("B11", 1500))}
    folder = tmp_path / "Sentinel-2_73.0250_31.0800_2023-01-01_2023-12-31"
    folder.mkdir()
    return write_tif(folder / f"{folder.name}.tif", bands)


def test_describe_reads_the_file_and_its_download_name(sentinel_tif):
    info = MapService().describe(str(sentinel_tif))

    assert (info.width, info.height, info.band_count) == (50, 40, 5)
    assert info.band_names == ("B2", "B3", "B4", "B8", "B11")
    assert info.crs == "EPSG:4326" and info.nodata == NODATA and info.dtype == "float32"
    assert info.bounds == pytest.approx((73.0, 31.06, 73.05, 31.1))
    assert (info.satellite, info.start_date, info.end_date) == ("Sentinel-2", "2023-01-01", "2023-12-31")
    assert info.size_bytes == sentinel_tif.stat().st_size


def test_describe_gives_bounds_in_degrees_for_other_projections(tmp_path):
    path = write_tif(tmp_path / "utm.tif", {"B1": np.zeros((10, 10))}, crs="EPSG:32643",
                     origin=(300000, 3500000), pixel=10)
    west, south, east, north = MapService().describe(str(path)).bounds
    assert 72 < west < east < 74 and 31 < south < north < 32


def test_unnamed_bands_get_numbered_names(tmp_path):
    path = tmp_path / "plain.tif"
    with rasterio.open(path, "w", driver="GTiff", width=4, height=4, count=2, dtype="uint8") as dst:
        dst.write(np.zeros((2, 4, 4), dtype="uint8"))
    assert MapService().describe(str(path)).band_names == ("Band 1", "Band 2")


def test_missing_or_broken_file_is_a_clear_error(tmp_path):
    with pytest.raises(MapError, match="missing or not a GeoTIFF"):
        MapService().describe(str(tmp_path / "nowhere.tif"))
    broken = tmp_path / "broken.tif"
    broken.write_text("not a raster")
    with pytest.raises(MapError):
        MapService().describe(str(broken))


# ------------------------------------------------------------------ band roles
from backend.business.map.band_roles import band_roles  # noqa: E402

S2 = ("B2", "B3", "B4", "B8", "B11")


@pytest.mark.parametrize("satellite, bands, expected", [
    ("Sentinel-2", S2, {"blue": "B2", "green": "B3", "red": "B4", "nir": "B8", "swir1": "B11"}),
    ("Landsat-8", ("SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6"),
     {"blue": "SR_B2", "green": "SR_B3", "red": "SR_B4", "nir": "SR_B5", "swir1": "SR_B6"}),
    ("Landsat-5", ("SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5"),
     {"blue": "SR_B1", "green": "SR_B2", "red": "SR_B3", "nir": "SR_B4", "swir1": "SR_B5"}),
    ("Sentinel-2", ("B4", "B8"), {"red": "B4", "nir": "B8"}),          # only the bands that were downloaded
    ("", S2, {"blue": "B2", "green": "B3", "red": "B4", "nir": "B8", "swir1": "B11"}),  # recognised by name
    ("", ("SR_B2", "SR_B3", "SR_B4"), {}),                              # Landsat 5 or 8? unknown
    ("Dynamic-World", ("label",), {}),
])
def test_band_roles(satellite, bands, expected):
    assert band_roles(satellite, bands) == expected


# ------------------------------------------------------------------ colour maps
from backend.business.map.colour_maps import DYNAMIC_WORLD_CLASSES, GREYS, VIRIDIS  # noqa: E402


def test_colour_map_blends_between_its_stops():
    table = GREYS.table()
    assert table.shape == (256, 3) and table.dtype == np.uint8
    assert table[0].tolist() == [0, 0, 0] and table[-1].tolist() == [255, 255, 255]
    assert GREYS.colours(3) == ("#000000", "#808080", "#FFFFFF")
    assert VIRIDIS.colours(2) == ("#440154", "#FDE725")


def test_colour_map_looks_up_values_and_clips_them():
    rgb = GREYS.apply(np.array([[-1.0, 0.0, 0.5, 1.0, 9.0, np.nan]]))
    assert rgb.shape == (1, 6, 3)
    assert rgb[0, :, 0].tolist() == [0, 0, 128, 255, 255, 0]


def test_dynamic_world_has_its_nine_classes():
    assert len(DYNAMIC_WORLD_CLASSES) == 9
    assert DYNAMIC_WORLD_CLASSES[0] == ("Water", "#419BDF") and DYNAMIC_WORLD_CLASSES[6][0] == "Built area"
