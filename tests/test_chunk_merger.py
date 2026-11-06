from pathlib import Path

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import Affine  # noqa: E402

from backend.business.download import ChunkMergeError, ChunkMerger  # noqa: E402
from backend.business.download import chunk_merger as merger_module  # noqa: E402
from backend.dto import ChunkDTO, FormDTO  # noqa: E402
from backend.dto.download_dto import CHUNK_MERGED  # noqa: E402

WIDTH, ROWS, PIXEL = 60, 25, 0.01


def _write_chunk(folder: Path, index: int, rows: int = ROWS, width: int = WIDTH, bands=("B4", "B8")) -> ChunkDTO:
    top = 35.0 - PIXEL * ROWS * index
    transform = (PIXEL, 0.0, 70.0, 0.0, -PIXEL, top)
    chunk = ChunkDTO(
        id=index + 1, bounds=(70.0, top - PIXEL * rows, 70.0 + PIXEL * width, top), crs="EPSG:4326",
        transform=transform, width=width, height=rows, row_offset=ROWS * index, bands=list(bands),
        size_bytes=width * rows * len(bands) * 4, file_path=str(folder / f"chunk_{index + 1:03d}.tif"),
        request=FormDTO(dataset="sentinel2_sr"),
    )
    with rasterio.open(chunk.file_path, "w", driver="GTiff", width=width, height=rows, count=len(bands),
                       dtype="float32", crs="EPSG:4326", transform=Affine(*transform), nodata=-9999.0) as ds:
        ds.write(np.full((len(bands), rows, width), index + 1, "float32"))
        for b, name in enumerate(bands, start=1):
            ds.set_band_description(b, name)
    return chunk


def _strip_values(path: str) -> list[int]:
    with rasterio.open(path) as src:
        band = src.read(1)
    return [int(band[row, 0]) for row in range(0, band.shape[0], ROWS)]


def test_two_chunks_become_one_file(tmp_path):
    chunks = [_write_chunk(tmp_path, 0), _write_chunk(tmp_path, 1)]
    dataset = ChunkMerger().merge(chunks)

    assert Path(dataset.path).name == "merged_001-002.tif"
    assert _strip_values(dataset.path) == [1, 2]
    with rasterio.open(dataset.path) as src:
        assert (src.width, src.height) == (WIDTH, 2 * ROWS)
        assert src.transform == Affine(*chunks[0].transform)
        assert src.descriptions == ("B4", "B8") and src.nodata == -9999.0
    assert dataset.source == "COPERNICUS/S2_SR_HARMONIZED" and dataset.bands == ["B4", "B8"]
    assert dataset.size_bytes == Path(dataset.path).stat().st_size


def test_merged_file_grows_one_chunk_at_a_time(tmp_path):
    """1 + 2 -> one file, + 3 -> bigger file, + 4 -> whole dataset."""
    merger = ChunkMerger()
    chunks = [_write_chunk(tmp_path, i) for i in range(4)]
    merged = chunks[0]
    for chunk in chunks[1:]:
        dataset = merger.merge([merged, chunk], output_path=str(tmp_path / f"merged_{chunk.id}.tif"))
        merged = merger.combined_chunk([merged, chunk], dataset)
        assert merged.height == chunk.row_offset + chunk.height

    assert _strip_values(dataset.path) == [1, 2, 3, 4]
    with rasterio.open(dataset.path) as src:
        assert src.bounds.top == 35.0 and src.bounds.bottom == pytest.approx(35.0 - 4 * ROWS * PIXEL)


def test_merged_chunks_are_marked_and_their_files_kept(tmp_path):
    chunks = [_write_chunk(tmp_path, 0), _write_chunk(tmp_path, 1)]
    ChunkMerger().merge(chunks)
    assert all(c.status == CHUNK_MERGED for c in chunks)
    assert all(Path(c.file_path).exists() for c in chunks)  # the caller deletes them


def test_large_chunks_are_copied_in_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(merger_module, "ROWS_PER_COPY", 7)  # 25 rows -> 4 copies per chunk
    dataset = ChunkMerger().merge([_write_chunk(tmp_path, 0), _write_chunk(tmp_path, 1)])
    assert _strip_values(dataset.path) == [1, 2]


def test_chunks_must_be_adjacent(tmp_path):
    chunks = [_write_chunk(tmp_path, 0), _write_chunk(tmp_path, 2)]
    with pytest.raises(ChunkMergeError, match="does not follow"):
        ChunkMerger().merge(chunks)


def test_chunks_must_share_the_grid(tmp_path):
    chunks = [_write_chunk(tmp_path, 0), _write_chunk(tmp_path, 1, width=WIDTH + 1)]
    with pytest.raises(ChunkMergeError, match="same grid"):
        ChunkMerger().merge(chunks)


def test_missing_chunk_file_is_an_error(tmp_path):
    chunk = _write_chunk(tmp_path, 0)
    Path(chunk.file_path).unlink()
    with pytest.raises(ChunkMergeError, match="not been downloaded"):
        ChunkMerger().merge([chunk])


def test_failed_merge_leaves_the_existing_file_untouched(tmp_path, monkeypatch):
    chunks = [_write_chunk(tmp_path, 0), _write_chunk(tmp_path, 1)]
    target = tmp_path / "merged.tif"
    target.write_bytes(b"previous merged file")
    monkeypatch.setattr(merger_module.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(OSError):
        ChunkMerger().merge(chunks, output_path=str(target))
    assert target.read_bytes() == b"previous merged file"
