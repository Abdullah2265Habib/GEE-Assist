"""Download settings and Google Earth Engine request limits."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Where downloads go unless the user picks another folder.
DEFAULT_DOWNLOAD_DIR = PROJECT_ROOT / "workspace" / "downloads"

# Output projections offered in the form. AUTO_UTM is replaced by the UTM zone
# of the AOI's centre (metre-based, good for area calculations).
AUTO_UTM = "AUTO_UTM"
CRS_OPTIONS: tuple[tuple[str, str], ...] = (
    ("EPSG:4326", "WGS 84 (EPSG:4326, degrees)"),
    (AUTO_UTM, "UTM zone of the AOI (metres)"),
    ("EPSG:3857", "Web Mercator (EPSG:3857)"),
)

# ee.Image.getDownloadURL limits: larger requests are refused, so the
# downloader splits the AOI into tiles that stay under both.
GEE_MAX_REQUEST_BYTES = 48 * 1024 * 1024   # 50 331 648 bytes
GEE_MAX_GRID_DIMENSION = 32_768            # pixels per side
BYTES_PER_PIXEL = 4                        # bands are exported as float32
