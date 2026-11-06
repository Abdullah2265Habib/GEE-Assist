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
from backend.exceptions import GEEError, GEERequestTooHeavyError, GEESetupError, ValidationError  # noqa: E402

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
                         max_request_bytes=chunk.width * tile_rows * len(chunk.bands) * 5, **kwargs)
        self.fetched: list[int] = []
        self.sent: list[int] = []      # size of each response, in bytes
        self.wrong_shape = False
        self.max_pixels: int | None = None  # bigger requests run out of memory, like a heavy composite
        self.requests: list[tuple[int, int]] = []  # (pixels asked for, refused?)

    def _initialize(self):
        pass

    def _build_image(self, form, bands):
        return "image"

    def _fetch_tile(self, image, chunk, tile):
        refused = self.max_pixels is not None and tile.width * tile.height > self.max_pixels
        self.requests.append((tile.width * tile.height, refused))
        if refused:
            raise GEERequestTooHeavyError("Earth Engine ran out of memory computing this request.")
        self.fetched.append(tile.index)
        shape = (1, 3, 3) if self.wrong_shape else None
        data = _tile_bytes(chunk, tile, tile.index + 1, shape)
        self.sent.append(len(data))
        return data


# ------------------------------------------------------------------ tiles
def test_tiles_stay_under_the_request_size():
    tiles = plan_tiles(66_800, 3_340, band_count=4, max_bytes=40_000_000)
    assert all(t.width * t.height * 4 * 5 <= 40_000_000 for t in tiles)  # GEE counts 5 bytes / pixel / band
    assert sum(t.width * t.height for t in tiles) == 66_800 * 3_340


def test_tiles_stay_under_gee_limit_as_gee_counts_it():
    """The chunk that failed: GEE reported a 6605 x 342 x 5-band tile as 56 472 750 bytes."""
    from backend.config import GEE_MAX_REQUEST_BYTES

    tiles = plan_tiles(6605, 2738, band_count=5)
    assert all(t.width * t.height * 5 * 5 <= GEE_MAX_REQUEST_BYTES for t in tiles)
    assert tiles[0].height < 342


def test_tiles_respect_the_32768_pixel_side_limit():
    tiles = plan_tiles(70_000, 10, band_count=1, max_bytes=10**12)
    assert max(t.width for t in tiles) == 32_768


def test_small_chunk_is_one_tile():
    assert len(plan_tiles(500, 400, band_count=3)) == 1


# ------------------------------------------------------------------ writing chunks
def test_chunk_is_written_tile_by_tile_on_the_chunk_grid(tmp_path):
    client, chunk, path = FakeGEEClient(), _chunk(), tmp_path / "chunk_001.tif"
    received = []

    assert client.fetch_chunk(chunk, str(path), on_progress=lambda raster, network: received.append((raster, network)))

    with rasterio.open(path) as src:
        pixels = src.read()
        assert src.transform == Affine(*chunk.transform)
        assert src.crs.to_string() == "EPSG:4326"
        assert src.descriptions == ("B4", "B8") and src.nodata == NODATA
    assert pixels.shape == (2, 40, 50)
    assert [pixels[0, row, 0] for row in (0, 10, 20, 30)] == [1, 2, 3, 4]  # 4 tiles of 10 rows
    assert [raster for raster, _ in received] == [50 * 10 * 2 * 4] * 4  # they add up to the chunk size
    assert [network for _, network in received] == client.sent  # what GEE sent
    assert not path.with_name(path.name + ".tiles.json").exists()


def test_stopped_chunk_continues_with_the_next_tile(tmp_path):
    client, chunk, path = FakeGEEClient(), _chunk(), tmp_path / "chunk_001.tif"
    done = []

    assert client.fetch_chunk(chunk, str(path), on_progress=lambda raster, network: done.append(raster), should_stop=lambda: len(done) == 2) is False
    assert json.loads(path.with_name(path.name + ".tiles.json").read_text()) == [0, 1]

    assert client.fetch_chunk(chunk, str(path)) is True
    assert client.fetched == [0, 1, 2, 3]  # nothing fetched twice
    with rasterio.open(path) as src:
        assert [src.read(1)[row, 0] for row in (0, 10, 20, 30)] == [1, 2, 3, 4]


def test_damaged_partial_chunk_is_downloaded_again(tmp_path):
    client, chunk, path = FakeGEEClient(), _chunk(), tmp_path / "chunk_001.tif"
    done = []
    client.fetch_chunk(chunk, str(path), on_progress=lambda raster, network: done.append(raster), should_stop=lambda: len(done) == 2)
    path.write_bytes(b"truncated when the app was killed")

    assert client.fetch_chunk(chunk, str(path)) is True
    assert client.fetched == [0, 1, 0, 1, 2, 3]  # started the chunk over
    with rasterio.open(path) as src:
        assert [src.read(1)[row, 0] for row in (0, 10, 20, 30)] == [1, 2, 3, 4]


def test_too_heavy_tile_is_fetched_in_quarters_and_later_tiles_start_small(tmp_path, monkeypatch):
    monkeypatch.setattr(gee_module, "MIN_SPLIT_PIXELS", 10)
    client, chunk, path = FakeGEEClient(), _chunk(), tmp_path / "chunk_001.tif"  # 4 tiles of 50 x 10
    client.max_pixels = 150
    received = []

    assert client.fetch_chunk(chunk, str(path), on_progress=lambda raster, network: received.append((raster, network)))

    assert client.requests[:5] == [(500, True)] + [(125, False)] * 4  # refused, then 4 quarters of 25 x 5
    assert client.requests[5:] == [(125, False)] * 12  # the other 3 tiles start in quarters: nothing refused
    with rasterio.open(path) as src:
        assert [src.read(1)[row, col] for row in (0, 14, 25, 39) for col in (0, 49)] == [1, 1, 2, 2, 3, 3, 4, 4]
    assert [raster for raster, _ in received] == [50 * 10 * 2 * 4] * 4  # progress per tile is unchanged
    assert sum(network for _, network in received) == sum(client.sent)


def test_tiles_are_split_again_until_they_fit(tmp_path, monkeypatch):
    monkeypatch.setattr(gee_module, "MIN_SPLIT_PIXELS", 10)
    client, chunk, path = FakeGEEClient(), _chunk(), tmp_path / "chunk_001.tif"
    client.max_pixels = 40  # 500 -> 125 (25 x 5) -> 39 (13 x 3) at most

    assert client.fetch_chunk(chunk, str(path))
    with rasterio.open(path) as src:
        assert [src.read(1)[row, 0] for row in (0, 10, 20, 39)] == [1, 2, 3, 4]
    refused = [r for _, r in client.requests]
    assert refused[:2] == [True, True] and not any(refused[2:])  # 500 px, then 125 px; nothing fails after that
    assert max(size for size, _ in client.requests[2:]) <= 40


def test_too_heavy_even_when_small_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(gee_module, "MIN_SPLIT_PIXELS", 200)
    client, chunk, path = FakeGEEClient(), _chunk(), tmp_path / "chunk_001.tif"
    client.max_pixels = 50  # quarters of 125 px are refused and too small to split again

    with pytest.raises(GEERequestTooHeavyError):
        client.fetch_chunk(chunk, str(path))


def test_quarters_cover_the_tile_exactly():
    tile = gee_module.Tile(index=3, col=10, row=20, width=5, height=1)
    parts = gee_module._quarters(tile)
    assert [(p.col, p.row, p.width, p.height) for p in parts] == [(10, 20, 3, 1), (13, 20, 2, 1)]
    assert all(p.index == 3 for p in parts)


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
    tile = plan_tiles(50, 40, 2, max_bytes=50 * 10 * 2 * 5)[2]  # rows 20-29

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
    with pytest.raises(ValidationError, match="No Sentinel-2"):  # retrying would not help
        GEEClient(project="p")._build_image(_form(), ["B4"])


# ------------------------------------------------------------------ access and errors
def test_missing_project_is_reported():
    with pytest.raises(GEESetupError, match="GEE_PROJECT"):
        GEEClient(project="")._initialize()
    assert GEEClient(project="").validate_access() is False


@pytest.mark.parametrize("raw, expected", [
    ("Google Earth Engine API has not been used in project x before or it is disabled.", "API is not enabled for project 'x'"),
    ("Please authorize access to your Earth Engine account", "earthengine authenticate"),
    ("Project 'x' is not registered to use Earth Engine", "Register it"),
    ("Too many concurrent aggregations", "busy"),
    ("User memory limit exceeded.", "Shorten the date range or use the mosaic composite"),
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


@pytest.mark.parametrize("raw", [
    "Google Earth Engine API has not been used in project x before or it is disabled.",
    "Please authorize access to your Earth Engine account",
    "Project 'x' is not registered to use Earth Engine",
])
def test_setup_problems_are_not_retried(raw):
    assert isinstance(gee_module._error(Exception(raw), "x"), GEESetupError)


def test_temporary_problems_are_retried():
    error = gee_module._error(Exception("Too many concurrent aggregations"), "x")
    assert type(error) is GEEError


@pytest.mark.parametrize("raw", ["User memory limit exceeded.", "Computation timed out.", "Earth Engine capacity exceeded."])
def test_too_heavy_requests_are_recognised(raw):
    assert isinstance(gee_module._error(Exception(raw), "x"), GEERequestTooHeavyError)
