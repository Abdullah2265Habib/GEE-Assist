"""GeminiClient: request building, answer parsing and error handling (no network)."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

from backend.data.clients.gemini_client import GeminiClient, QueryInterpretation, interpretation_to_form
from backend.data.clients.prompts import build_query_system_prompt
from backend.data.data_facade import DataFacade
from backend.exceptions import LLMServiceError


class FakeModels:
    """Answers with ``text``; ``errors`` maps a model name to a list of errors raised first."""

    def __init__(self, text: str | None = None, error: Exception | None = None, errors: dict | None = None):
        self.text, self.calls = text, []
        self.errors = errors if errors is not None else ({"*": [error] * 99} if error else {})

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        queue = self.errors.get(model) or self.errors.get("*")
        if queue:
            raise queue.pop(0)
        return SimpleNamespace(text=self.text)


def client_answering(text=None, error=None, errors=None, fallbacks=()) -> tuple[GeminiClient, FakeModels]:
    models = FakeModels(text, error, errors)
    client = GeminiClient(api_key="unused", model="gemini-test", client=SimpleNamespace(models=models),
                          fallback_models=fallbacks, sleep=lambda _seconds: None)
    return client, models


def server_error(code: int, status: str, message: str) -> Exception:
    error_class = genai_errors.ServerError if code >= 500 else genai_errors.ClientError
    return error_class(code, {"error": {"code": code, "message": message, "status": status}})


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
        (server_error(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key."), "API key"),
        (server_error(403, "PERMISSION_DENIED", "Permission denied"), "API key"),
        (server_error(429, "RESOURCE_EXHAUSTED", "Quota exceeded"), "usage limit"),
        (server_error(503, "UNAVAILABLE", "This model is currently experiencing high demand."), "busy"),
        (server_error(404, "NOT_FOUND", "models/gemini-test is no longer available"), "no longer available"),
        (OSError("getaddrinfo failed"), "internet"),
        (RuntimeError("something odd"), "couldn't process"),
    ],
)
def test_api_errors_become_short_plain_messages(error, phrase):
    client, _ = client_answering(error=error)
    with pytest.raises(LLMServiceError, match=phrase) as raised:
        client.process_query("q")
    message = str(raised.value)
    for raw in ("{", "error", "code", "404", "503", "429", "UNAVAILABLE", "NOT_FOUND"):
        assert raw not in message, message


def test_busy_model_is_retried_after_a_short_wait():
    busy = server_error(503, "UNAVAILABLE", "high demand")
    waits = []
    models = FakeModels(json.dumps(ANSWER), errors={"gemini-test": [busy]})
    client = GeminiClient(api_key="unused", model="gemini-test", client=SimpleNamespace(models=models),
                          fallback_models=(), sleep=waits.append)
    assert client.process_query("q").dataset == "sentinel2_sr"
    assert [c["model"] for c in models.calls] == ["gemini-test"] * 2 and len(waits) == 1


def test_all_models_busy_gives_a_plain_busy_message():
    busy = server_error(503, "UNAVAILABLE", "high demand")
    client, models = client_answering(errors={"*": [busy] * 9}, fallbacks=("gemini-next",))
    with pytest.raises(LLMServiceError, match="busy"):
        client.process_query("q")
    assert len(models.calls) == 4  # two models, two rounds


def test_retired_model_falls_back_to_the_next_and_remembers_it():
    gone = server_error(404, "NOT_FOUND", "no longer available to new users")
    client, models = client_answering(json.dumps(ANSWER), errors={"gemini-test": [gone] * 9}, fallbacks=("gemini-next",))
    assert client.process_query("q").dataset == "sentinel2_sr"
    assert [c["model"] for c in models.calls] == ["gemini-test", "gemini-next"]
    client.process_query("again")
    assert models.calls[-1]["model"] == "gemini-next"  # no second failed call to the retired model


def test_busy_model_is_skipped_for_the_next_one():
    busy = server_error(503, "UNAVAILABLE", "high demand")
    client, models = client_answering(json.dumps(ANSWER), errors={"gemini-test": [busy] * 9}, fallbacks=("gemini-next",))
    assert client.process_query("q").dataset == "sentinel2_sr"
    assert [c["model"] for c in models.calls] == ["gemini-test", "gemini-next"]  # no waiting on a busy model


def test_model_over_its_limit_is_skipped_for_the_next_one():
    limit = server_error(429, "RESOURCE_EXHAUSTED", "You exceeded your current quota")
    client, models = client_answering(json.dumps(ANSWER), errors={"gemini-test": [limit] * 9}, fallbacks=("gemini-next",))
    assert client.process_query("q").dataset == "sentinel2_sr"
    assert [c["model"] for c in models.calls] == ["gemini-test", "gemini-next"]


def test_key_errors_are_not_retried():
    client, models = client_answering(error=server_error(403, "PERMISSION_DENIED", "denied"), fallbacks=("gemini-next",))
    with pytest.raises(LLMServiceError, match="API key"):
        client.process_query("q")
    assert len(models.calls) == 1


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
