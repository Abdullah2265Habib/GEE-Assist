from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

from backend.business.download.i_chunk_merger import IChunkMerger
from backend.config import get_dataset
from backend.dto import ChunkDTO, DatasetDTO
from backend.dto.download_dto import CHUNK_MERGED
from backend.exceptions import GeeAssistError

ROWS_PER_COPY = 512   # rows copied at a time, so merging a large file needs little memory


class ChunkMergeError(GeeAssistError):
    """The chunks cannot be joined (missing files, gaps, different grids)."""


class ChunkMerger(IChunkMerger):
    """Class diagram: ChunkMerger. Stacks strips on the shared output grid.

    Writes to a temporary file first and renames it when complete, so an interrupted
    merge never damages an existing merged file.
    """

    def merge(
        self,
        chunks: list[ChunkDTO],
        output_path: Optional[str] = None,
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> DatasetDTO:
        import rasterio
        from rasterio.transform import Affine
        from rasterio.windows import Window

        if not chunks:
            raise ChunkMergeError("There are no chunks to merge.")
        _check_adjacent(chunks)
        first = chunks[0]
        target = Path(output_path) if output_path else Path(first.file_path).with_name(
            f"merged_{first.id:03d}-{chunks[-1].id:03d}.tif"
        )
        partial = target.with_name(target.name + ".part")
        height = sum(chunk.height for chunk in chunks)

        with rasterio.open(first.file_path) as template:
            profile = template.profile
            descriptions = template.descriptions
        profile.update(
            height=height, width=first.width, transform=Affine(*first.transform),
            tiled=True, blockxsize=256, blockysize=256, BIGTIFF="IF_SAFER",
        )

        with rasterio.open(partial, "w", **profile) as dst:
            for index, name in enumerate(descriptions, start=1):
                if name:
                    dst.set_band_description(index, name)
            for chunk in chunks:
                top = chunk.row_offset - first.row_offset
                with rasterio.open(chunk.file_path) as src:
                    for row in range(0, chunk.height, ROWS_PER_COPY):
                        rows = min(ROWS_PER_COPY, chunk.height - row)
                        block = src.read(window=Window(0, row, chunk.width, rows))
                        dst.write(block, window=Window(0, top + row, chunk.width, rows))
                        if on_progress:
                            on_progress(block.nbytes)
        os.replace(partial, target)

        for chunk in chunks:
            chunk.status = CHUNK_MERGED
        info = get_dataset(first.request.dataset) if first.request else None
        return DatasetDTO(
            id=target.stem,
            source=info.collection_id if info else "",
            path=str(target),
            bands=list(first.bands),
            size_bytes=target.stat().st_size,
        )

    @staticmethod
    def combined_chunk(chunks: list[ChunkDTO], dataset: DatasetDTO) -> ChunkDTO:
        """A chunk standing for the merged file, so it can be merged with the next chunk."""
        first = chunks[0]
        return ChunkDTO(
            id=first.id,
            bounds=(first.bounds[0], chunks[-1].bounds[1], first.bounds[2], first.bounds[3]),
            crs=first.crs,
            transform=first.transform,
            width=first.width,
            height=sum(chunk.height for chunk in chunks),
            row_offset=first.row_offset,
            bands=list(first.bands),
            size_bytes=sum(chunk.size_bytes for chunk in chunks),
            status=CHUNK_MERGED,
            file_path=dataset.path,
            request=first.request,
        )


def _check_adjacent(chunks: list[ChunkDTO]) -> None:
    for chunk in chunks:
        if not chunk.file_path or not Path(chunk.file_path).exists():
            raise ChunkMergeError(f"Chunk {chunk.id} has not been downloaded.")
    first = chunks[0]
    for upper, lower in zip(chunks, chunks[1:]):
        if lower.row_offset != upper.row_offset + upper.height:
            raise ChunkMergeError(f"Chunk {lower.id} does not follow chunk {upper.id}.")
        if (lower.width, lower.crs, lower.bands, lower.transform[:3]) != (first.width, first.crs, first.bands, first.transform[:3]):
            raise ChunkMergeError(f"Chunk {lower.id} is not on the same grid as chunk {first.id}.")
