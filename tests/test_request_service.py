"""RequestService.submit_query: UC-02 Enter Natural Language Query + Interpret Query."""

from __future__ import annotations

import json
from datetime import date

import pytest

from backend.business.request import RequestService
from backend.business.request.query_interpretation import check_interpretation
from backend.config.limits import MAX_QUERY_LENGTH
from backend.data.i_data_facade import IDataFacade
from backend.dto import FormDTO
from backend.exceptions import LLMServiceError, ValidationError

BOX = json.dumps({"type": "Polygon", "coordinates": [[[73, 31], [73.2, 31], [73.2, 31.2], [73, 31.2], [73, 31]]]})
TODAY = date(2026, 11, 6)


class FakeDataFacade(IDataFacade):
    def __init__(self, answer: FormDTO | None = None, error: Exception | None = None):
        self.answer, self.error, self.prompts = answer, error, []

    def process_query(self, prompt: str) -> FormDTO:
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.answer


# ------------------------------------------------------------------ submit_query
def test_query_is_cleaned_sent_and_not_kept():
    facade = FakeDataFacade(FormDTO(dataset="sentinel2_sr", aoi=BOX, start_date=date(2024, 1, 1), end_date=date(2024, 2, 1)))
    service = RequestService(data_facade=facade)
    form = service.submit_query("  NDVI   for\n Faisalabad  ")
    assert facade.prompts == ["NDVI for Faisalabad"]
    assert form.source == "nl" and form.query_text == "NDVI for Faisalabad"
    assert form.bands  # filled with the dataset defaults
    assert service.get_kept_requests() == []  # kept only when the user submits the form


@pytest.mark.parametrize("text", ["", "   ", None, "x" * (MAX_QUERY_LENGTH + 1)])
def test_empty_or_too_long_query_is_rejected_before_gemini(text):
    facade = FakeDataFacade(FormDTO())
    with pytest.raises(ValidationError):
        RequestService(data_facade=facade).submit_query(text)
    assert facade.prompts == []


def test_without_gemini_a_clear_error_is_raised():
    with pytest.raises(LLMServiceError):
        RequestService().submit_query("NDVI for Lahore")


def test_gemini_errors_reach_the_caller():
    service = RequestService(data_facade=FakeDataFacade(error=LLMServiceError("quota reached")))
    with pytest.raises(LLMServiceError, match="quota"):
        service.submit_query("NDVI for Lahore")


# ----------------------------------------------------------- check_interpretation
def test_unknown_dataset_keeps_only_place_and_time():
    form = check_interpretation(
        FormDTO(dataset="planet_scope", bands=["B1"], aoi=BOX, start_date=date(2024, 1, 1),
                end_date=date(2024, 2, 1), analysis_type="Water", processes=["NDWI"]),
        TODAY,
    )
    assert form.dataset == "" and form.bands == [] and form.analysis_type == ""
    assert form.aoi == BOX and form.start_date == date(2024, 1, 1)
    assert any("unsupported dataset" in n for n in form.notes)


def test_bands_processes_and_analysis_are_limited_to_the_dataset():
    form = check_interpretation(
        FormDTO(dataset="sentinel1_grd", bands=["VV", "B4"], analysis_type="Water", processes=["NDWI", "WaterBodyDetection"]),
        TODAY,
    )
    assert form.bands == ["VV"] and form.processes == ["WaterBodyDetection"]
    assert len(form.notes) == 2


def test_unsupported_analysis_is_cleared():
    form = check_interpretation(FormDTO(dataset="modis_lst", analysis_type="Vegetation", processes=["NDVI"]), TODAY)
    assert form.analysis_type == "" and form.processes == []
    assert form.bands == ["LST_Day_1km"]  # defaults when none given
    assert form.scale == 1000 and form.composite == "median"


def test_cloud_cover_dropped_for_datasets_without_it():
    assert check_interpretation(FormDTO(dataset="sentinel1_grd", max_cloud_cover=10), TODAY).max_cloud_cover is None
    assert check_interpretation(FormDTO(dataset="sentinel2_sr", max_cloud_cover=10), TODAY).max_cloud_cover == 10


def test_dates_are_swapped_and_clamped_to_the_archive():
    form = check_interpretation(
        FormDTO(dataset="sentinel2_sr", start_date=date(2027, 1, 1), end_date=date(2016, 1, 1)), TODAY
    )
    assert form.start_date == date(2017, 3, 28) and form.end_date == TODAY
    assert len(form.notes) == 2


def test_dates_entirely_outside_a_discontinued_archive_are_dropped():
    form = check_interpretation(
        FormDTO(dataset="landsat5_l2", start_date=date(2020, 1, 1), end_date=date(2020, 6, 1)), TODAY
    )
    assert form.start_date is None and form.end_date is None


def test_invalid_area_is_dropped():
    flat = json.dumps({"type": "Polygon", "coordinates": [[[1, 1], [1, 1], [1, 1], [1, 1]]]})
    form = check_interpretation(FormDTO(dataset="sentinel2_sr", aoi=flat), TODAY)
    assert form.aoi == "" and any("area" in n for n in form.notes)
