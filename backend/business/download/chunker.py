from __future__ import annotations

import math

from backend.business.download.i_chunker import IChunker
from backend.business.download.output_grid import OutputGrid, output_grid
from backend.config.download_settings import DownloadSettingsStore
from backend.dto import ChunkDTO, FormDTO


class Chunker(IChunker):
    """Class diagram: Chunker. Cuts the output grid into full-width horizontal strips.

    The number of chunks is ``ceil(total size / chunk size)``, so a 2 GB dataset with
    500 MB chunks gives 4 chunks. Rows are shared out evenly, so the chunks differ by
    at most one row. The chunk size is read from the settings file on every split,
    so a changed size applies to the next download.
    """

    def __init__(self, settings: DownloadSettingsStore):
        self._settings = settings

    def split(self, form: FormDTO) -> list[ChunkDTO]:
        grid = output_grid(form)
        count = min(grid.height, max(1, math.ceil(grid.total_bytes / self._settings.load().chunk_size_bytes)))
        base, extra = divmod(grid.height, count)

        chunks: list[ChunkDTO] = []
        row = 0
        for index in range(count):
            rows = base + (1 if index < extra else 0)
            chunks.append(self._chunk(grid, index + 1, row, rows, form))
            row += rows
        return chunks

    @staticmethod
    def _chunk(grid: OutputGrid, chunk_id: int, row_offset: int, rows: int, form: FormDTO) -> ChunkDTO:
        top = grid.row_top(row_offset)
        bottom = grid.row_top(row_offset + rows)
        return ChunkDTO(
            id=chunk_id,
            bounds=(grid.west, bottom, grid.east, top),
            crs=grid.crs,
            transform=(grid.pixel_size, 0.0, grid.west, 0.0, -grid.pixel_size, top),
            width=grid.width,
            height=rows,
            row_offset=row_offset,
            bands=list(grid.bands),
            size_bytes=grid.row_bytes * rows,
            request=form,
        )
