"""IGeminiClient implementation using the ``google-genai`` SDK."""

from __future__ import annotations

import json
import logging
import time
from datetime import date

from pydantic import BaseModel, Field

from backend.data.clients.i_gemini_client import IGeminiClient
from backend.config.llm import FALLBACK_MODELS
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
    def __init__(self, api_key: str, model: str, client=None, fallback_models=FALLBACK_MODELS, sleep=time.sleep):
        """``client`` lets tests pass a fake ``genai.Client``; ``sleep`` lets them skip the waits."""
        self._api_key = api_key
        # Try the configured model first, then current fallbacks (no duplicates, order kept).
        self._models = list(dict.fromkeys([model, *fallback_models]))
        self._client = client
        self._sleep = sleep

    def process_query(self, prompt: str) -> FormDTO:
        raw = self._generate(prompt, build_query_system_prompt())
        try:
            data = QueryInterpretation.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as exc:
            log.warning("Unusable Gemini answer: %s", raw[:500])
            raise LLMServiceError("Gemini's answer couldn't be read. Please try again.") from exc
        return interpretation_to_form(data, prompt)

    def generate_explanation(self, result) -> str:
        raise NotImplementedError("UC-08 Get AI Explanation is not part of this delivery.")

    # ------------------------------------------------------------------ internals
    def _sdk(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise LLMServiceError("Gemini isn't set up yet. Add your API key as GEMINI_API_KEY in the .env file.")
        try:
            from google import genai
        except ImportError as exc:
            raise LLMServiceError("Gemini support isn't installed. Run: pip install -r requirements.txt") from exc
        self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _generate(self, contents: str, system_instruction: str) -> str:
        """Call Gemini. A busy or retired model is skipped for the next one; if all are
        busy, wait briefly and try once more. Only a short, plain message reaches the user."""
        sdk = self._sdk()
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=QueryInterpretation,
        )
        last_kind = "other"
        for round_number in range(RETRY_ROUNDS):
            if round_number:
                self._sleep(RETRY_WAIT_SEC)  # every model was busy: give Gemini a moment
            for model in list(self._models):
                try:
                    response = sdk.models.generate_content(model=model, contents=contents, config=config)
                except Exception as exc:  # the full error goes to the log, never to the user
                    last_kind = _classify(exc)
                    log.warning("Gemini %s failed (%s): %s", model, last_kind, exc)
                    if last_kind == "model":
                        self._models.remove(model)  # retired: don't try it again this session
                        continue
                    if last_kind in ("busy", "quota"):
                        continue  # overloaded, or this model's limit is used up: try the next one
                    raise LLMServiceError(USER_MESSAGES[last_kind]) from exc

                text = (getattr(response, "text", None) or "").strip()
                if not text:
                    raise LLMServiceError("Gemini didn't return an answer. Please rephrase and try again.")
                if model != self._models[0]:
                    reason = {"model": "is retired", "quota": "reached its usage limit"}.get(last_kind, "was busy")
                    log.warning("Gemini model %s %s; using %s for this session.", self._models[0], reason, model)
                    self._models.remove(model)
                    self._models.insert(0, model)
                return text
        raise LLMServiceError(USER_MESSAGES["model" if not self._models else last_kind])


# ----------------------------------------------------------------------------- error handling
# When every model is busy, wait this long and go through them once more.
RETRY_ROUNDS = 2
RETRY_WAIT_SEC = 2.0

USER_MESSAGES = {
    "key": "Gemini didn't accept the API key. Check GEMINI_API_KEY in the .env file.",
    "quota": "The Gemini usage limit has been reached. Please wait a minute and try again.",
    "busy": "Gemini is busy right now. Please try again in a moment.",
    "model": "The Gemini model is no longer available. Set a current model in GEMINI_MODEL in the .env file.",
    "network": "Can't reach Gemini. Check your internet connection and try again.",
    "other": "Gemini couldn't process the request. Please try again.",
}


def _classify(exc: Exception) -> str:
    """Sort an SDK / network error into one of the USER_MESSAGES kinds."""
    code = getattr(exc, "code", None)
    status = str(getattr(exc, "status", "") or "").upper()
    text = str(exc).lower()
    if code in (401, 403) or status in ("UNAUTHENTICATED", "PERMISSION_DENIED") or "api key" in text or "api_key" in text:
        return "key"
    if code == 429 or status == "RESOURCE_EXHAUSTED" or "quota" in text:
        return "quota"
    if code == 404 or status == "NOT_FOUND":
        return "model"
    if (isinstance(code, int) and code >= 500) or status in ("UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED"):
        return "busy"
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)) or any(
        word in text for word in ("getaddrinfo", "connection", "timed out", "timeout", "network")
    ):
        return "network"
    return "other"
