"""IGeminiClient implementation using the ``google-genai`` SDK."""

from __future__ import annotations

import json
import logging
from datetime import date

from pydantic import BaseModel, Field

from backend.data.clients.i_gemini_client import IGeminiClient
from backend.data.clients.prompts import build_query_system_prompt
from backend.dto import FormDTO
from backend.exceptions import LLMServiceError

log = logging.getLogger(__name__)


class QueryInterpretation(BaseModel):
    """JSON schema Gemini must answer with (structured output)."""

    dataset: str = ""
    bands: list[str] = Field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    aoi_name: str = ""
    aoi_bbox: list[float] = Field(default_factory=list)
    max_cloud_cover: int = -1
    scale_m: int = 0
    composite: str = ""
    analysis_type: str = ""
    processes: list[str] = Field(default_factory=list)
    clarification: str = ""


def bbox_to_geojson(bbox: list[float]) -> str:
    min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox)
    ring = [[min_lon, min_lat], [max_lon, min_lat], [max_lon, max_lat], [min_lon, max_lat], [min_lon, min_lat]]
    return json.dumps({"type": "Polygon", "coordinates": [ring]})


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip()[:10]) if value and value.strip() else None
    except ValueError:
        return None


def interpretation_to_form(data: QueryInterpretation, query: str) -> FormDTO:
    """Map Gemini's answer onto a FormDTO (no catalogue checks here)."""
    aoi = ""
    if len(data.aoi_bbox) == 4:
        try:
            aoi = bbox_to_geojson(data.aoi_bbox)
        except (TypeError, ValueError):
            aoi = ""
    return FormDTO(
        dataset=data.dataset.strip(),
        bands=[b.strip() for b in data.bands if b.strip()],
        scale=data.scale_m if data.scale_m > 0 else None,
        max_cloud_cover=data.max_cloud_cover if 0 <= data.max_cloud_cover <= 100 else None,
        composite=data.composite.strip(),
        aoi=aoi,
        aoi_name=data.aoi_name.strip(),
        start_date=_parse_date(data.start_date),
        end_date=_parse_date(data.end_date),
        analysis_type=data.analysis_type.strip(),
        processes=[p.strip() for p in data.processes if p.strip()],
        source="nl",
        query_text=query,
        clarification=data.clarification.strip(),
    )


class GeminiClient(IGeminiClient):
    def __init__(self, api_key: str, model: str, client=None):
        """``client`` lets tests pass a fake ``genai.Client``."""
        self._api_key = api_key
        self._model = model
        self._client = client

    def process_query(self, prompt: str) -> FormDTO:
        raw = self._generate(prompt, build_query_system_prompt())
        try:
            data = QueryInterpretation.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as exc:
            log.warning("Unusable Gemini answer: %s", raw[:500])
            raise LLMServiceError("Gemini returned an answer that could not be read. Please try again.") from exc
        return interpretation_to_form(data, prompt)

    def generate_explanation(self, result) -> str:
        raise NotImplementedError("UC-08 Get AI Explanation is not part of this delivery.")

    # ------------------------------------------------------------------ internals
    def _sdk(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise LLMServiceError(
                "Gemini is not set up. Add GEMINI_API_KEY to the .env file in the project folder."
            )
        try:
            from google import genai
        except ImportError as exc:
            raise LLMServiceError("The google-genai package is not installed (pip install google-genai).") from exc
        self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _generate(self, contents: str, system_instruction: str) -> str:
        sdk = self._sdk()
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=QueryInterpretation,
        )
        try:
            response = sdk.models.generate_content(model=self._model, contents=contents, config=config)
        except LLMServiceError:
            raise
        except Exception as exc:  # network, invalid key, quota / rate limit (C-08), ...
            log.warning("Gemini request failed: %s", exc)
            raise LLMServiceError(f"Gemini request failed: {_friendly(exc)}") from exc

        text = (getattr(response, "text", None) or "").strip()
        if not text:
            raise LLMServiceError("Gemini returned an empty answer. Please rephrase and try again.")
        return text


def _friendly(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()
    if "api key" in lowered or "api_key" in lowered or "permission" in lowered or "401" in message or "403" in message:
        return "the API key was rejected. Check GEMINI_API_KEY."
    if "429" in message or "quota" in lowered or "rate" in lowered:
        return "the Gemini quota or rate limit was reached. Wait a moment and try again."
    if "getaddrinfo" in lowered or "connection" in lowered or "timed out" in lowered:
        return "no connection to Gemini. Check your internet connection."
    return message[:200]
