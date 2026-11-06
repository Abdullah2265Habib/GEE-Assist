"""GEEClient against a fake Earth Engine: tiling, writing chunks, resuming, image building, errors."""

import json
from datetime import date
from unittest.mock import MagicMock

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.io import MemoryFile  # noqa: E402
from rasterio.transform import Affine  # noqa: E402

from backend.data.clients import gee_client as gee_module  # noqa: E402
from backend.data.clients.gee_client import NODATA, GEEClient  # noqa: E402
from backend.data.clients.gee_tiles import plan_tiles  # noqa: E402
from backend.data.data_facade import DataFacade  # noqa: E402
from backend.dto import ChunkDTO, FormDTO  # noqa: E402
from backend.exceptions import GEEError  # noqa: E402

SQUARE = {"type": "Polygon", "coordinates": [[[73.0, 31.0], [73.1, 31.0], [73.1, 31.1], [73.0, 31.1], [73.0, 31.0]]]}


def _chunk(width=50, height=40, bands=("B4", "B8")) -> ChunkDTO:
    form = FormDTO(dataset="sentinel2_sr", bands=list(bands), aoi=json.dumps(SQUARE))
    return ChunkDTO(1, (70, 34.6, 70.5, 35), "EPSG:4326", (0.01, 0.0, 70.0, 0.0, -0.01, 35.0),
                    width, height, 0, list(bands), request=form)


def _tile_bytes(chunk: ChunkDTO, tile, value: float, shape=None) -> bytes:
    a, _, c, _, e, f = chunk.transform
    bands, height, width = shape or (len(chunk.bands), tile.height, tile.width)
    with MemoryFile() as memory:
        with memory.open(driver="GTiff", width=width, height=height, count=bands, dtype="float32",
                         crs=chunk.crs, transform=Affine(a, 0, c + a * tile.col, 0, e, f + e * tile.row)) as ds:
            ds.write(np.full((bands, height, width), value, "float32"))
        return memory.read()


class FakeGEEClient(GEEClient):
    """Real tiling and file writing; every tile is filled with (its index + 1)."""

    def __init__(self, tile_rows=10, **kwargs):
        chunk = _chunk()
        super().__init__(project="test", parallel_requests=1,
                         max_request_bytes=chunk.width * tile_rows * len(chunk.bands) * 4, **kwargs)
        self.fetched: list[int] = []
        self.wrong_shape = False

    def _initialize(self):
        pass

    def _build_image(self, form, bands):
        return "image"

    def _fetch_tile(self, image, chunk, tile):
        self.fetched.append(tile.index)
        shape = (1, 3, 3) if self.wrong_shape else None
        return _tile_bytes(chunk, tile, tile.index + 1, shape)


# ------------------------------------------------------------------ tiles
def test_tiles_stay_under_the_request_size():
    tiles = plan_tiles(66_800, 3_340, band_count=4, max_bytes=40_000_000)
    assert all(t.width * t.height * 4 * 4 <= 40_000_000 for t in tiles)
    assert sum(t.width * t.height for t in tiles) == 66_800 * 3_340


def test_tiles_respect_the_32768_pixel_side_limit():
    tiles = plan_tiles(70_000, 10, band_count=1, max_bytes=10**12)
    assert max(t.width for t in tiles) == 32_768


def test_small_chunk_is_one_tile():
    assert len(plan_tiles(500, 400, band_count=3)) == 1


# ------------------------------------------------------------------ writing chunks
def test_chunk_is_written_tile_by_tile_on_the_chunk_grid(tmp_path):
    client, chunk, path = FakeGEEClient(), _chunk(), tmp_path / "chunk_001.tif"
    received = []

    assert client.fetch_chunk(chunk, str(path), on_progress=received.append)

    with rasterio.open(path) as src:
        pixels = src.read()
        assert src.transform == Affine(*chunk.transform)
        assert src.crs.to_string() == "EPSG:4326"
        assert src.descriptions == ("B4", "B8") and src.nodata == NODATA
    assert pixels.shape == (2, 40, 50)
    assert [pixels[0, row, 0] for row in (0, 10, 20, 30)] == [1, 2, 3, 4]  # 4 tiles of 10 rows
    assert len(received) == 4 and all(n > 0 for n in received)
    assert not path.with_name(path.name + ".tiles.json").exists()


def test_stopped_chunk_continues_with_the_next_tile(tmp_path):
    client, chunk, path = FakeGEEClient(), _chunk(), tmp_path / "chunk_001.tif"
    done = []

    assert client.fetch_chunk(chunk, str(path), on_progress=done.append, should_stop=lambda: len(done) == 2) is False
    assert json.loads(path.with_name(path.name + ".tiles.json").read_text()) == [0, 1]

    assert client.fetch_chunk(chunk, str(path)) is True
    assert client.fetched == [0, 1, 2, 3]  # nothing fetched twice
    with rasterio.open(path) as src:
        assert [src.read(1)[row, 0] for row in (0, 10, 20, 30)] == [1, 2, 3, 4]


def test_tile_of_the_wrong_shape_is_an_error(tmp_path):
    client = FakeGEEClient()
    client.wrong_shape = True
    with pytest.raises(GEEError):
        client.fetch_chunk(_chunk(), str(tmp_path / "chunk_001.tif"))


def test_chunk_without_a_request_is_an_error(tmp_path):
    chunk = _chunk()
    chunk.request = None
    with pytest.raises(GEEError):
        FakeGEEClient().fetch_chunk(chunk, str(tmp_path / "c.tif"))


def test_tile_request_shifts_the_grid_to_the_tile_corner(monkeypatch):
    ee = MagicMock()
    monkeypatch.setattr(GEEClient, "_ee", staticmethod(lambda: ee))
    chunk = _chunk()
    tile = plan_tiles(50, 40, 2, max_bytes=50 * 10 * 2 * 4)[2]  # rows 20-29

    GEEClient(project="p")._fetch_tile("image", chunk, tile)

    grid = ee.data.computePixels.call_args[0][0]["grid"]
    assert grid["dimensions"] == {"width": 50, "height": 10}
    assert grid["affineTransform"]["translateX"] == 70.0
    assert grid["affineTransform"]["translateY"] == pytest.approx(35.0 - 0.01 * 20)
    assert grid["crsCode"] == "EPSG:4326"


# ------------------------------------------------------------------ building the image
@pytest.fixture
def fake_ee(monkeypatch):
    ee = MagicMock()
    collection = ee.ImageCollection.return_value
    for step in ("filterBounds", "filterDate", "filter"):
        getattr(collection, step).return_value = collection
    collection.size.return_value.getInfo.return_value = 3
    monkeypatch.setattr(GEEClient, "_ee", staticmethod(lambda: ee))
    return ee, collection


def _form(**overrides) -> FormDTO:
    values = dict(dataset="sentinel2_sr", bands=["B4", "B8"], aoi=json.dumps(SQUARE),
                  start_date=date(2024, 6, 1), end_date=date(2024, 8, 31), composite="median")
    values.update(overrides)
    return FormDTO(**values)


def test_image_uses_the_collection_dates_and_composite(fake_ee):
    ee, collection = fake_ee
    GEEClient(project="p")._build_image(_form(), ["B4", "B8"])

    ee.ImageCollection.assert_called_once_with("COPERNICUS/S2_SR_HARMONIZED")
    collection.filterDate.assert_called_once_with("2024-06-01", "2024-09-01")  # end date included
    collection.median.return_value.select.assert_called_once_with(["B4", "B8"])


def test_image_applies_the_cloud_limit_with_the_dataset_property(fake_ee):
    ee, collection = fake_ee
    GEEClient(project="p")._build_image(_form(max_cloud_cover=20), ["B4"])
    ee.Filter.lte.assert_called_once_with("CLOUDY_PIXEL_PERCENTAGE", 20)


def test_mosaic_composite(fake_ee):
    _, collection = fake_ee
    GEEClient(project="p")._build_image(_form(composite="mosaic"), ["B4"])
    collection.mosaic.assert_called_once()


def test_no_matching_images_is_a_clear_error(fake_ee):
    _, collection = fake_ee
    collection.size.return_value.getInfo.return_value = 0
    with pytest.raises(GEEError, match="No Sentinel-2"):
        GEEClient(project="p")._build_image(_form(), ["B4"])


# ------------------------------------------------------------------ access and errors
def test_missing_project_is_reported():
    with pytest.raises(GEEError, match="GEE_PROJECT"):
        GEEClient(project="")._initialize()
    assert GEEClient(project="").validate_access() is False


@pytest.mark.parametrize("raw, expected", [
    ("Please authorize access to your Earth Engine account", "earthengine authenticate"),
    ("Project 'x' is not registered to use Earth Engine", "Register it"),
    ("Too many concurrent aggregations", "busy"),
    ("Something else", "refused the request: Something else"),
])
def test_earth_engine_errors_are_explained(raw, expected):
    assert expected in gee_module._explain(Exception(raw), "x")


def test_data_facade_delegates_to_the_gee_client(tmp_path):
    client = FakeGEEClient()
    facade = DataFacade(gemini_client=MagicMock(), gee_client=client)
    assert facade.fetch_chunk(_chunk(), str(tmp_path / "c.tif")) is True


def test_data_facade_without_a_gee_client():
    facade = DataFacade(gemini_client=MagicMock())
    assert facade.validate_access() is False
    with pytest.raises(GEEError):
        facade.fetch_chunk(_chunk(), "c.tif")
