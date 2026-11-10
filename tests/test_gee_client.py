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
        self.watch = None                  # a file whose size is noted at each request
        self.sizes: list[int] = []

    def _initialize(self):
        pass

    def _build_image(self, form, bands):
        return "image"

    def _fetch_tile(self, image, chunk, tile, on_bytes, stop):
        if self.watch is not None:
            self.sizes.append(self.watch.stat().st_size)
        refused = self.max_pixels is not None and tile.width * tile.height > self.max_pixels
        self.requests.append((tile.width * tile.height, refused))
        if refused:
            raise GEERequestTooHeavyError("Earth Engine ran out of memory computing this request.")
        self.fetched.append(tile.index)
        shape = (1, 3, 3) if self.wrong_shape else None
        data = _tile_bytes(chunk, tile, tile.index + 1, shape)
        self.sent.append(len(data))
        half = len(data) // 2  # arrives in two parts, like a streamed response
        on_bytes(half, half)
        on_bytes(len(data) - half, len(data) - half)
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
    assert sum(raster for raster, _ in received) == 50 * 40 * 2 * 4  # progress adds up to the chunk size
    assert sum(network for _, network in received) == sum(client.sent)  # what GEE sent
    assert received[0][0] > 0 and received[0][1] > 0  # progress shows while the first tile arrives
    assert not path.with_name(path.name + ".tiles.json").exists()


def test_each_tile_is_on_disk_before_the_next_is_requested(tmp_path):
    client, chunk, path = FakeGEEClient(), _chunk(), tmp_path / "chunk_001.tif"
    client.watch = path
    assert client.fetch_chunk(chunk, str(path))
    # The 50 x 40 test chunk fits in one 256 x 256 block: the block is on disk as soon as the first
    # tile is written (it used to stay in memory until the end), so the file is full from then on.
    assert client.sizes[0] < 100 and client.sizes[1] > 50 * 40 * 2 * 4


def test_stopped_chunk_continues_with_the_next_tile(tmp_path):
    client, chunk, path = FakeGEEClient(), _chunk(), tmp_path / "chunk_001.tif"

    assert client.fetch_chunk(chunk, str(path), should_stop=lambda: len(client.fetched) == 2) is False
    assert json.loads(path.with_name(path.name + ".tiles.json").read_text()) == [0, 1]

    assert client.fetch_chunk(chunk, str(path)) is True
    assert client.fetched == [0, 1, 2, 3]  # nothing fetched twice
    with rasterio.open(path) as src:
        assert [src.read(1)[row, 0] for row in (0, 10, 20, 30)] == [1, 2, 3, 4]


def test_damaged_partial_chunk_is_downloaded_again(tmp_path):
    client, chunk, path = FakeGEEClient(), _chunk(), tmp_path / "chunk_001.tif"
    client.fetch_chunk(chunk, str(path), should_stop=lambda: len(client.fetched) == 2)
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
    assert sum(raster for raster, _ in received) == 50 * 40 * 2 * 4  # progress is unchanged
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

    sent = []
    monkeypatch.setattr(GEEClient, "_compute_pixels", lambda self, request, on_bytes, stop: sent.append(request))
    GEEClient(project="p")._fetch_tile("image", chunk, tile, lambda *a: None, lambda: False)

    grid = sent[0]["grid"]
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


# ------------------------------------------------------------------ set-up checks
def _statuses(checks):
    return [(check.name, check.status) for check in checks]


def test_diagnose_without_the_library(monkeypatch):
    def missing():
        raise GEESetupError("The Earth Engine library is missing: pip install earthengine-api")

    monkeypatch.setattr(GEEClient, "_ee", staticmethod(missing))
    checks = GEEClient(project="p").diagnose()
    assert _statuses(checks) == [
        ("Earth Engine library", "fail"), ("Cloud project (GEE_PROJECT)", "ok"),
        ("Sign-in on this computer", "skip"), ("Connection", "skip"), ("Test request", "skip"),
    ]
    assert "pip install earthengine-api" in checks[0].hint


def test_diagnose_without_a_project(fake_ee, tmp_path, monkeypatch):
    ee, _ = fake_ee
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    ee.oauth.get_credentials_path.return_value = str(tmp_path / "credentials")
    checks = GEEClient(project="").diagnose()
    assert _statuses(checks)[1:] == [
        ("Cloud project (GEE_PROJECT)", "fail"), ("Sign-in on this computer", "warn"),
        ("Connection", "skip"), ("Test request", "skip"),
    ]
    assert "GEE_PROJECT" in checks[1].hint and str(tmp_path / "credentials") in checks[2].detail
    ee.Initialize.assert_not_called()


def test_diagnose_when_everything_works(fake_ee, tmp_path):
    ee, _ = fake_ee
    credentials = tmp_path / "credentials"
    credentials.write_text("{}")
    ee.oauth.get_credentials_path.return_value = str(credentials)
    ee.__version__ = "1.7.48"
    checks = GEEClient(project="my-project").diagnose()
    assert all(check.status == "ok" for check in checks), _statuses(checks)
    assert checks[0].detail == "earthengine-api 1.7.48" and checks[1].detail == "my-project"
    assert str(credentials) in checks[2].detail
    ee.Initialize.assert_called_once_with(project="my-project")
    assert checks[4].duration_ms is not None and "answered in" in checks[4].detail


def test_diagnose_reports_a_failed_connection(fake_ee, tmp_path, monkeypatch):
    ee, _ = fake_ee
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    ee.oauth.get_credentials_path.return_value = str(tmp_path / "missing")
    ee.Initialize.side_effect = Exception("Please authorize access to your Earth Engine account")
    checks = GEEClient(project="p").diagnose()
    assert _statuses(checks)[2:] == [("Sign-in on this computer", "warn"), ("Connection", "fail"), ("Test request", "skip")]
    assert "earthengine authenticate" in checks[3].detail


def test_diagnose_reports_a_failed_test_request(fake_ee):
    ee, _ = fake_ee
    ee.Number.return_value.getInfo.side_effect = Exception("Project 'p' is not registered to use Earth Engine")
    checks = GEEClient(project="p").diagnose()
    assert checks[3].status == "ok" and checks[4].status == "fail" and "Register it" in checks[4].detail


def test_signing_in_connects_again_with_the_new_credentials(fake_ee):
    ee, _ = fake_ee
    sign_in = MagicMock()
    sign_in.begin.return_value = "https://accounts.google.com/o/oauth2/auth?client_id=x"
    sign_in.wait.return_value = "C:/Users/me/.config/earthengine/credentials"
    client = GEEClient(project="p", sign_in=sign_in)
    client._initialize()

    assert client.begin_sign_in().startswith("https://accounts.google.com/")
    stop = MagicMock(return_value=False)
    assert client.complete_sign_in(stop).endswith("credentials")
    sign_in.wait.assert_called_once_with(stop)
    client._initialize()
    assert ee.Initialize.call_count == 2  # connected again after signing in
    client.cancel_sign_in()
    sign_in.cancel.assert_called_once_with()


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
    assert [check.status for check in facade.diagnose_gee()] == ["fail"]
    with pytest.raises(GEEError):
        facade.begin_gee_sign_in()
    facade.cancel_gee_sign_in()  # nothing to cancel


def test_data_facade_delegates_the_checks_and_sign_in_to_the_gee_client():
    client = MagicMock()
    facade = DataFacade(gemini_client=MagicMock(), gee_client=client)
    assert facade.diagnose_gee() is client.diagnose.return_value
    assert facade.begin_gee_sign_in() is client.begin_sign_in.return_value
    stop = MagicMock()
    assert facade.complete_gee_sign_in(stop) is client.complete_sign_in.return_value
    client.complete_sign_in.assert_called_once_with(stop)
    facade.cancel_gee_sign_in()
    client.cancel_sign_in.assert_called_once_with()


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


# ------------------------------------------------------------------ streaming responses
class FakeResponse:
    def __init__(self, blocks, status=200, error=None):
        self.status_code, self._blocks, self._error = status, blocks, error
        self.raw = MagicMock()
        self.raw.tell.side_effect = [sum(len(b) for b in blocks[:i + 1]) // 2 for i in range(len(blocks))]  # gzip

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_content(self, size):
        yield from self._blocks

    def json(self):
        return {"error": {"message": self._error}}


def _streaming_client(monkeypatch, response):
    ee = MagicMock()
    ee.EEException = RuntimeError
    monkeypatch.setattr(GEEClient, "_ee", staticmethod(lambda: ee))
    session = MagicMock()
    session.request.return_value = response
    client = GEEClient(project="p")
    monkeypatch.setattr(client, "_session", lambda credentials: session)
    return client, session


def test_response_is_reported_while_it_streams_in(monkeypatch):
    client, session = _streaming_client(monkeypatch, FakeResponse([b"a" * 100, b"b" * 60]))
    seen = []

    data = client._compute_pixels({"expression": "image"}, lambda network, payload: seen.append((network, payload)),
                                  lambda: False)

    assert data == b"a" * 100 + b"b" * 60
    assert seen == [(50, 100), (30, 60)]  # network bytes (compressed) and response bytes, block by block
    assert session.request.call_args.kwargs["stream"] is True


def test_earth_engine_error_response_is_raised_with_its_message(monkeypatch):
    client, _ = _streaming_client(monkeypatch, FakeResponse([], status=400, error="User memory limit exceeded."))
    with pytest.raises(RuntimeError, match="User memory limit exceeded"):
        client._compute_pixels({"expression": "image"}, lambda *a: None, lambda: False)


def test_pause_stops_a_streaming_response(monkeypatch):
    client, _ = _streaming_client(monkeypatch, FakeResponse([b"a" * 10, b"b" * 10]))
    with pytest.raises(gee_module._Stopped):
        client._compute_pixels({"expression": "image"}, lambda *a: None, lambda: True)


def test_progress_of_unwritten_tiles_is_taken_back():
    events = []
    reporter = gee_module._ChunkReporter(lambda raster, network: events.append((raster, network)))
    first, second = reporter.receiver(0, 100), reporter.receiver(1, 100)
    first(40, 60)
    second(30, 150)          # more than the tile's raster size: progress stops at 100
    reporter.written(1, 100)
    reporter.close()         # tile 0 was not written: its 60 come back off
    first(10, 10)            # an abandoned request finishing later is ignored

    assert events == [(60, 40), (100, 30), (-60, 0)]
