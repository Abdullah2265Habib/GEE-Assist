"""IGeocodingClient on OpenStreetMap's Nominatim service.

Nominatim returns the administrative boundary of cities, districts, provinces
and countries as GeoJSON, which becomes the AOI exactly as mapped.

Usage policy (https://operations.osmfoundation.org/policies/nominatim/): at most
one request per second and an identifying User-Agent. Searches only run when the
user asks for one (no search-as-you-type), and calls are spaced a second apart.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable

import httpx

from backend.data.clients.i_geocoding_client import IGeocodingClient
from backend.dto import PlaceDTO
from backend.exceptions import PlaceSearchError

NOMINATIM_URL = "https://nominatim.openstreetmap.org"
# Nominatim simplifies the outline to this tolerance (degrees, ~50 m) before sending it.
POLYGON_THRESHOLD_DEG = 0.0005
MIN_REQUEST_INTERVAL_S = 1.0

_UNREACHABLE = "Couldn't reach the place search service. Check your internet connection and try again."


class NominatimClient(IGeocodingClient):
    def __init__(
        self,
        base_url: str = NOMINATIM_URL,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
        min_interval: float = MIN_REQUEST_INTERVAL_S,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": "GEE-Assist-Desktop"},
        )
        self._min_interval = min_interval
        self._clock, self._sleep = clock, sleep
        self._lock = threading.Lock()
        self._last_request: float | None = None

    def close(self) -> None:
        self._http.close()

    def search(self, query: str, limit: int = 5) -> list[PlaceDTO]:
        params = {
            "q": query,
            "format": "jsonv2",
            "polygon_geojson": 1,
            "polygon_threshold": POLYGON_THRESHOLD_DEG,
            "limit": limit,
            "accept-language": "en",
        }
        with self._lock:  # one request at a time, a second apart
            self._wait_turn()
            try:
                response = self._http.get("/search", params=params)
            except httpx.HTTPError as exc:
                raise PlaceSearchError(_UNREACHABLE) from exc
            finally:
                self._last_request = self._clock()

        if response.status_code == 429:
            raise PlaceSearchError("The place search service is busy. Wait a moment and try again.")
        if response.status_code != 200:
            raise PlaceSearchError(f"The place search service failed (HTTP {response.status_code}). Try again later.")
        try:
            results = response.json()
        except ValueError as exc:
            raise PlaceSearchError("The place search service sent an unreadable answer. Try again later.") from exc
        if not isinstance(results, list):
            raise PlaceSearchError("The place search service sent an unreadable answer. Try again later.")
        return [place for place in (_to_place(item) for item in results) if place is not None]

    def _wait_turn(self) -> None:
        if self._last_request is None:
            return
        remaining = self._min_interval - (self._clock() - self._last_request)
        if remaining > 0:
            self._sleep(remaining)


def _to_place(item: Any) -> PlaceDTO | None:
    if not isinstance(item, dict) or not isinstance(item.get("geojson"), dict):
        return None
    display_name = str(item.get("display_name") or "").strip()
    name = str(item.get("name") or "").strip() or display_name.split(",")[0].strip()
    if not name:
        return None
    kind = str(item.get("addresstype") or item.get("type") or "place").replace("_", " ")
    return PlaceDTO(name=name, display_name=display_name or name, kind=kind, aoi=json.dumps(item["geojson"]))
