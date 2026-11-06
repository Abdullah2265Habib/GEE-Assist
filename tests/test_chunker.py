import json

import pytest

from backend.business.download import chunker as chunker_module
from backend.business.download.chunker import Chunker
from backend.business.download.output_grid import METRES_PER_DEGREE, OutputGrid, output_grid
from backend.config.download_settings import DownloadSettings, DownloadSettingsStore
from backend.dto import FormDTO
from backend.exceptions import ValidationError

MB = 1_000_000  # chunk sizes are decimal megabytes
SQUARE = {"type": "Polygon", "coordinates": [[[73.0, 31.0], [73.1, 31.0], [73.1, 31.1], [73.0, 31.1], [73.0, 31.0]]]}


def _form(**overrides) -> FormDTO:
    values = dict(dataset="sentinel2_sr", bands=["B4", "B8"], scale=10, aoi=json.dumps(SQUARE), crs="EPSG:4326")
    values.update(overrides)
    return FormDTO(**values)


@pytest.fixture
def store(tmp_path):
    return DownloadSettingsStore(tmp_path / "download_settings.json")


def _use_grid(monkeypatch, width: int, height: int, bands: int = 1) -> OutputGrid:
    """Make the chunker see a grid of an exact size (1 band of float32 = 4 bytes / pixel)."""
    grid = OutputGrid("EPSG:4326", 70.0, 35.0, 0.001, width, height, tuple(f"B{i}" for i in range(bands)))
    monkeypatch.setattr(chunker_module, "output_grid", lambda form: grid)
    return grid


# ------------------------------------------------------------------ output grid
def test_grid_in_degrees_uses_gee_metres_per_degree():
    grid = output_grid(_form(crs="EPSG:4326"))
    assert grid.pixel_size == pytest.approx(10 / METRES_PER_DEGREE)
    assert grid.width == grid.height == 1114  # 0.1 degree / (10 m in degrees)


def test_grid_in_utm_uses_metres():
    grid = output_grid(_form(crs="EPSG:32643"))
    assert grid.pixel_size == 10
    assert 950 < grid.width < 1000 and 1100 < grid.height < 1150  # ~9.6 km x ~11.1 km at 31 N


def test_grid_size_counts_every_band_as_float32():
    grid = output_grid(_form(bands=["B2", "B3", "B4"]))
    assert grid.total_bytes == grid.width * grid.height * 3 * 4


def test_grid_needs_an_aoi():
    with pytest.raises(ValidationError):
        output_grid(_form(aoi=""))


# ------------------------------------------------------------------ chunking
def test_2_gb_with_500_mb_chunks_gives_4_chunks(store, monkeypatch):
    _use_grid(monkeypatch, width=1000, height=500_000)  # 1000 px * 4 B = 4000 B per row -> 2 GB
    chunks = Chunker(store).split(_form())

    assert len(chunks) == 4
    assert all(chunk.size_bytes == 500 * MB for chunk in chunks)


def test_chunks_never_exceed_the_chunk_size_by_more_than_a_row(store, monkeypatch):
    grid = _use_grid(monkeypatch, width=1000, height=300_001)
    store.save(DownloadSettings(chunk_size_mb=100))
    chunks = Chunker(store).split(_form())

    assert len(chunks) == 13  # 1200.0012 MB / 100 MB, rounded up
    assert max(c.size_bytes for c in chunks) <= 100 * MB + grid.row_bytes
    assert max(c.height for c in chunks) - min(c.height for c in chunks) <= 1


def test_chunks_cover_the_grid_top_to_bottom_without_gaps(store, monkeypatch):
    grid = _use_grid(monkeypatch, width=2000, height=70_001)
    store.save(DownloadSettings(chunk_size_mb=100))
    chunks = Chunker(store).split(_form())

    assert [c.id for c in chunks] == list(range(1, len(chunks) + 1))
    assert chunks[0].row_offset == 0
    for upper, lower in zip(chunks, chunks[1:]):
        assert lower.row_offset == upper.row_offset + upper.height
        assert lower.bounds[3] == pytest.approx(upper.bounds[1])  # top of one = bottom of the one above
    assert chunks[-1].row_offset + chunks[-1].height == grid.height


def test_chunk_transform_places_the_strip_on_the_grid(store, monkeypatch):
    grid = _use_grid(monkeypatch, width=100, height=50)
    chunk = Chunker(store).split(_form())[0]

    assert chunk.transform == (grid.pixel_size, 0.0, grid.west, 0.0, -grid.pixel_size, grid.north)
    assert (chunk.width, chunk.height, chunk.crs) == (100, 50, "EPSG:4326")


def test_small_download_is_a_single_chunk(store):
    chunks = Chunker(store).split(_form())
    assert len(chunks) == 1 and chunks[0].size_bytes < 500 * MB


def test_every_chunk_carries_the_request_and_bands(store):
    form = _form()
    chunk = Chunker(store).split(form)[0]
    assert chunk.request is form and chunk.bands == ["B4", "B8"]


def test_changed_chunk_size_applies_to_the_next_split(store, monkeypatch):
    _use_grid(monkeypatch, width=1000, height=500_000)  # 2 GB
    chunker = Chunker(store)
    assert len(chunker.split(_form())) == 4
    store.set_chunk_size_mb(1024)
    assert len(chunker.split(_form())) == 2
