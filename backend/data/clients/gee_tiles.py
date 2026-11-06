"""Cut a chunk into GEE requests that stay under Earth Engine's per-request limits.

One computePixels / getDownloadURL request may return at most 48 MB and at most
32 768 pixels per side, so a 500 MB chunk is fetched as a grid of smaller tiles.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.config import BYTES_PER_PIXEL, GEE_MAX_GRID_DIMENSION, GEE_MAX_REQUEST_BYTES

# Aim below the hard limit: GEE adds the GeoTIFF header and rounds sizes its own way.
TARGET_REQUEST_BYTES = int(GEE_MAX_REQUEST_BYTES * 0.9)


@dataclass(frozen=True)
class Tile:
    index: int
    col: int      # pixel offset inside the chunk
    row: int
    width: int
    height: int


def plan_tiles(
    width: int,
    height: int,
    band_count: int,
    max_bytes: int = TARGET_REQUEST_BYTES,
    max_dimension: int = GEE_MAX_GRID_DIMENSION,
) -> list[Tile]:
    """Tiles covering a ``width`` x ``height`` chunk, row by row, each within the limits.

    Tiles are as wide as possible (full chunk width when it fits) so each request
    returns long, contiguous rows.
    """
    pixel_bytes = max(1, band_count) * BYTES_PER_PIXEL
    tile_width = max(1, min(width, max_dimension, max_bytes // pixel_bytes))
    tile_height = max(1, min(height, max_dimension, max_bytes // (tile_width * pixel_bytes)))

    tiles: list[Tile] = []
    for row in range(0, height, tile_height):
        for col in range(0, width, tile_width):
            tiles.append(Tile(
                index=len(tiles),
                col=col,
                row=row,
                width=min(tile_width, width - col),
                height=min(tile_height, height - row),
            ))
    return tiles
