"""RequestService.submit_query: UC-02 Enter Natural Language Query + Interpret Query."""

from __future__ import annotations

import json
from datetime import date

import pytest

from backend.business.request import RequestService
from backend.business.request.query_entities import QueryEntityExtractor
from backend.business.request.query_interpretation import check_interpretation, ground_with_entities
from backend.config.limits import MAX_QUERY_LENGTH
from backend.data.i_data_facade import IDataFacade
from backend.dto import FormDTO
from backend.exceptions import LLMServiceError, ValidationError

BOX = json.dumps({"type": "Polygon", "coordinates": [[[73, 31], [73.2, 31], [73.2, 31.2], [73, 31.2], [73, 31]]]})
TODAY = date(2026, 11, 6)


class FakeDataFacade(IDataFacade):
    def __init__(self, answer: FormDTO | None = None, error: Exception | None = None, places=()):
        self.answer, self.error, self.prompts = answer, error, []
        self.places, self.place_queries = list(places), []

    def process_query(self, prompt: str) -> FormDTO:
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.answer

    def search_places(self, query):
        self.place_queries.append(query)
        return self.places

    def fetch_chunk(self, chunk, path, on_progress=None, should_stop=None) -> bool:  # not used here
        raise NotImplementedError

    def validate_access(self) -> bool:
        return False

    def diagnose_gee(self):  # not used here
        return []

    def begin_gee_sign_in(self) -> str:  # not used here
        raise NotImplementedError

    def complete_gee_sign_in(self, should_stop=None) -> str:  # not used here
        raise NotImplementedError

    def cancel_gee_sign_in(self) -> None:  # not used here
        pass


# ------------------------------------------------------------------ submit_query
RULES_ONLY = QueryEntityExtractor(use_spacy=False, today=TODAY)  # deterministic, no spaCy model needed


def service_with(facade=None) -> RequestService:
    return RequestService(data_facade=facade, entity_extractor=RULES_ONLY)


def test_query_is_cleaned_sent_with_entity_hints_and_not_kept():
    facade = FakeDataFacade(FormDTO(dataset="sentinel2_sr", aoi=BOX, start_date=date(2024, 1, 1), end_date=date(2024, 2, 1)))
    service = service_with(facade)
    form = service.submit_query("  NDVI   for\n Faisalabad  ")
    prompt = facade.prompts[0]
    assert prompt.startswith("NDVI for Faisalabad")
    assert 'PROCESS: "NDVI"' in prompt and 'PLACE: "Faisalabad"' in prompt
    assert form.source == "nl" and form.query_text == "NDVI for Faisalabad"
    assert form.analysis_type == "Vegetation" and form.processes == ["NDVI"]  # from the entity
    assert form.bands  # filled with the dataset defaults
    assert [e.label for e in form.entities] == ["PROCESS", "PLACE"]
    assert service.get_kept_requests() == []  # kept only when the user submits the form


@pytest.mark.parametrize("text", ["", "   ", None, "x" * (MAX_QUERY_LENGTH + 1)])
def test_empty_or_too_long_query_is_rejected_before_gemini(text):
    facade = FakeDataFacade(FormDTO())
    with pytest.raises(ValidationError):
        service_with(facade).submit_query(text)
    assert facade.prompts == []


def test_gemini_errors_reach_the_caller_when_nothing_is_recognised():
    service = service_with(FakeDataFacade(error=LLMServiceError("Gemini is busy right now.")))
    with pytest.raises(LLMServiceError, match="busy"):
        service.submit_query("show me something nice")


def test_without_gemini_and_nothing_recognised_a_clear_error_is_raised():
    with pytest.raises(LLMServiceError):
        service_with(None).submit_query("show me something nice")


def test_when_gemini_fails_the_form_is_filled_from_entities():
    service = service_with(FakeDataFacade(error=LLMServiceError("Gemini is busy right now.")))
    form = service.submit_query("Landsat 8 NDVI for Faisalabad in 2023, under 15% clouds, at 30 m")
    assert form.dataset == "landsat8_l2" and form.processes == ["NDVI"] and form.analysis_type == "Vegetation"
    assert (form.start_date, form.end_date) == (date(2023, 1, 1), date(2023, 12, 31))
    assert form.max_cloud_cover == 15 and form.scale == 30
    assert form.aoi == "" and form.aoi_name == "Faisalabad"
    assert form.notes[0].startswith("Gemini is busy right now.")
    assert any("draw the area" in n for n in form.notes)


# ------------------------------------------------------------ ground_with_entities
def entities(text: str):
    return RULES_ONLY.extract(text)


def test_named_dataset_overrides_gemini():
    gemini = FormDTO(dataset="sentinel2_sr", bands=["B4", "B8"])
    form = ground_with_entities(gemini, entities("Landsat 8 data for Multan"))
    assert form.dataset == "landsat8_l2" and form.bands == []  # Sentinel-2 bands no longer apply
    assert any("Landsat 8" in n and "Gemini suggested" in n for n in form.notes)


def test_two_named_datasets_leave_gemini_to_choose():
    form = ground_with_entities(FormDTO(dataset="landsat9_l2"), entities("Sentinel-2 or Landsat 8 for Multan"))
    assert form.dataset == "landsat9_l2"


def test_named_processes_bands_cloud_resolution_and_composite_win():
    gemini = FormDTO(dataset="landsat8_l2", analysis_type="Water", processes=["NDWI"], max_cloud_cover=50, scale=60)
    form = ground_with_entities(gemini, entities("EVI with bands SR_B4 and SR_B5, cloud-free, 30 m resolution, mean composite"))
    assert form.analysis_type == "Vegetation" and form.processes == ["EVI"]
    assert form.bands == ["SR_B4", "SR_B5"]
    assert (form.max_cloud_cover, form.scale, form.composite) == (10, 30, "mean")


def test_gemini_extra_processes_in_the_same_category_are_kept():
    gemini = FormDTO(analysis_type="Vegetation", processes=["NDVI", "SAVI"])
    assert ground_with_entities(gemini, entities("NDVI please")).processes == ["NDVI", "SAVI"]


def test_dates_from_entities_only_fill_gaps():
    gemini = FormDTO(start_date=date(2024, 6, 1), end_date=date(2024, 8, 31))
    assert ground_with_entities(gemini, entities("NDVI in 2020")).start_date == date(2024, 6, 1)
    assert ground_with_entities(FormDTO(), entities("NDVI in 2020")).end_date == date(2020, 12, 31)


def test_a_place_from_the_entities_names_the_area():
    assert ground_with_entities(FormDTO(), entities("NDVI for Sahiwal")).aoi_name == "Sahiwal"


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
