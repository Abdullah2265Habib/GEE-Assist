"""GeminiClient: request building, answer parsing and error handling (no network)."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from backend.data.clients.gemini_client import GeminiClient, QueryInterpretation, interpretation_to_form
from backend.data.clients.prompts import build_query_system_prompt
from backend.data.data_facade import DataFacade
from backend.exceptions import LLMServiceError


class FakeModels:
    def __init__(self, text: str | None = None, error: Exception | None = None):
        self.text, self.error, self.calls = text, error, []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)


def client_answering(text=None, error=None) -> tuple[GeminiClient, FakeModels]:
    models = FakeModels(text, error)
    return GeminiClient(api_key="unused", model="gemini-test", client=SimpleNamespace(models=models)), models


ANSWER = {
    "dataset": "sentinel2_sr", "bands": ["B4", "B8"], "start_date": "2024-06-01", "end_date": "2024-08-31",
    "aoi_name": "Faisalabad", "aoi_bbox": [72.9, 31.3, 73.2, 31.5], "max_cloud_cover": 20, "scale_m": 0,
    "composite": "", "analysis_type": "Vegetation", "processes": ["NDVI"], "clarification": "",
}


def test_process_query_sends_structured_request_and_maps_answer():
    client, models = client_answering(json.dumps(ANSWER))
    form = client.process_query("NDVI for Faisalabad last summer")

    call = models.calls[0]
    assert call["model"] == "gemini-test" and call["contents"] == "NDVI for Faisalabad last summer"
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].response_schema is QueryInterpretation
    assert call["config"].temperature == 0.0

    assert form.dataset == "sentinel2_sr" and form.bands == ["B4", "B8"]
    assert (form.start_date, form.end_date) == (date(2024, 6, 1), date(2024, 8, 31))
    assert json.loads(form.aoi)["coordinates"][0][0] == [72.9, 31.3]
    assert form.aoi_name == "Faisalabad" and form.max_cloud_cover == 20
    assert form.scale is None and form.source == "nl" and form.query_text == "NDVI for Faisalabad last summer"


def test_missing_values_become_empty_fields():
    form = interpretation_to_form(QueryInterpretation(clarification="Which city?"), "show me data")
    assert form.dataset == "" and form.aoi == "" and form.start_date is None
    assert form.max_cloud_cover is None and form.clarification == "Which city?"


def test_bad_dates_and_bbox_are_dropped():
    data = QueryInterpretation(start_date="last june", end_date="2024-13-40", aoi_bbox=[1, 2, 3])
    form = interpretation_to_form(data, "q")
    assert form.start_date is None and form.end_date is None and form.aoi == ""


@pytest.mark.parametrize("text", ["not json", "", "[1, 2]", '{"bands": "B4"}'])
def test_unusable_answers_raise(text):
    client, _ = client_answering(text)
    with pytest.raises(LLMServiceError):
        client.process_query("q")


@pytest.mark.parametrize(
    "error, phrase",
    [
        (RuntimeError("401 API key not valid"), "API key"),
        (RuntimeError("429 RESOURCE_EXHAUSTED quota"), "quota"),
        (OSError("getaddrinfo failed"), "internet"),
    ],
)
def test_api_errors_become_readable_llm_errors(error, phrase):
    client, _ = client_answering(error=error)
    with pytest.raises(LLMServiceError, match=phrase):
        client.process_query("q")


def test_missing_api_key_is_reported():
    with pytest.raises(LLMServiceError, match="GEMINI_API_KEY"):
        GeminiClient(api_key="", model="m").process_query("q")


def test_prompt_lists_catalogue_and_today():
    prompt = build_query_system_prompt(date(2026, 11, 6))
    assert "2026-11-06" in prompt
    for key in ("sentinel2_sr", "landsat9_l2", "sentinel1_grd", "dynamic_world", "jrc_water_monthly"):
        assert f'"{key}"' in prompt


def test_data_facade_delegates_to_gemini():
    client, models = client_answering(json.dumps(ANSWER))
    assert DataFacade(gemini_client=client).process_query("q").dataset == "sentinel2_sr"
    assert len(models.calls) == 1
