"""Named-entity classifier for natural-language queries."""

from __future__ import annotations

from datetime import date

import pytest

from backend.business.request.query_entities import (
    QueryEntityExtractor,
    date_range,
    format_entity_hints,
)

TODAY = date(2026, 11, 6)
RULES = QueryEntityExtractor(use_spacy=False, today=TODAY)

try:
    import spacy

    spacy.load("en_core_web_sm")
    HAS_SPACY_MODEL = True
except Exception:  # spaCy or its model not installed
    HAS_SPACY_MODEL = False


def found(extractor, text, label):
    return [(e.text, e.value) for e in extractor.extract(text) if e.label == label]


# ----------------------------------------------------------------------------- domain terms (rules)
@pytest.mark.parametrize(
    "text, key",
    [
        ("Sentinel-2 imagery", "sentinel2_sr"),
        ("sentinel 2 l1c", "sentinel2_toa"),
        ("data from landsat8", "landsat8_l2"),
        ("Landsat 9 L2 scenes", "landsat9_l2"),
        ("radar images", "sentinel1_grd"),
        ("MOD11A2 product", "modis_lst"),
        ("ERA5-Land temperatures", "era5_land_daily"),
        ("Dynamic World labels", "dynamic_world"),
    ],
)
def test_datasets_are_recognised_from_aliases(text, key):
    assert [value for _, value in found(RULES, text, "DATASET")] == [key]


def test_longest_alias_wins():
    assert found(RULES, "Sentinel-2 L1C over Lahore", "DATASET") == [("Sentinel-2 L1C", "sentinel2_toa")]


@pytest.mark.parametrize(
    "text, process",
    [("NDVI", "NDVI"), ("enhanced vegetation index", "EVI"), ("flood mapping", "WaterBodyDetection"),
     ("water area", "WaterAreaEstimation"), ("land surface temperature", "LSTMapping"),
     ("urban expansion", "LULCChangeDetection")],
)
def test_processes_are_recognised(text, process):
    assert [value for _, value in found(RULES, f"{text} for Multan", "PROCESS")] == [process]


def test_analysis_words_inside_a_process_are_not_repeated():
    labels = [e.label for e in RULES.extract("water bodies and vegetation")]
    assert labels.count("ANALYSIS") == 1 and "PROCESS" in labels


def test_only_code_like_band_names_are_bands():
    assert [v for _, v in found(RULES, "bands B4, B8A and VV for crops", "BAND")] == ["B4", "B8A", "VV"]
    assert found(RULES, "NDVI of crops", "BAND") == []  # NDVI is a process, crops a word


@pytest.mark.parametrize(
    "text, percent",
    [("under 20% clouds", "20"), ("cloud cover below 15 %", "15"), ("max 5 percent cloud", "5"),
     ("cloud-free images", "10"), ("clouds less than 30%", "30")],
)
def test_cloud_cover(text, percent):
    assert [v for _, v in found(RULES, text, "CLOUD_COVER")] == [percent]


@pytest.mark.parametrize("text, metres", [("at 30 m", "30"), ("10m resolution", "10"), ("1 km pixels", "1000")])
def test_resolution(text, metres):
    assert [v for _, v in found(RULES, text, "RESOLUTION")] == [metres]


def test_distance_is_not_a_resolution():
    assert found(RULES, "within 50 km of Lahore", "RESOLUTION") == []


@pytest.mark.parametrize("text, method", [("median composite", "median"), ("average NDVI", "mean"), ("max composite", "max")])
def test_composite(text, method):
    assert [v for _, v in found(RULES, text, "COMPOSITE")] == [method]


# ----------------------------------------------------------------------------- dates
@pytest.mark.parametrize(
    "text, expected",
    [
        ("from June to August 2024", "2024-06-01/2024-08-31"),
        ("between 2018 and 2024", "2018-01-01/2024-12-31"),
        ("in 2023", "2023-01-01/2023-12-31"),
        ("March 2022", "2022-03-01/2022-03-31"),
        ("since 2020", "2020-01-01/2026-11-06"),
        ("the past 2 years", "2024-11-06/2026-11-06"),
        ("last three months", "2026-08-06/2026-11-06"),
        ("November to February 2025", "2024-11-01/2025-02-28"),
    ],
)
def test_explicit_dates_get_a_range(text, expected):
    assert [v for _, v in found(RULES, f"NDVI {text}", "DATE")] == [expected]


def test_vague_dates_are_kept_without_a_range():
    assert found(RULES, "for the last three summers", "DATE") == [("the last three summers", "")]


def test_date_range_takes_the_widest_span():
    ents = RULES.extract("NDVI in 2019 and in 2022")
    assert date_range(ents) == (date(2019, 1, 1), date(2022, 12, 31))


# ----------------------------------------------------------------------------- places
def test_capitalised_places_after_cues_without_spacy():
    assert [v for _, v in found(RULES, "NDVI for Faisalabad and Sahiwal", "PLACE")] == ["Faisalabad", "Sahiwal"]


def test_sensor_names_are_not_places():
    assert found(RULES, "MODIS data for Gilgit with Landsat", "PLACE") == [("Gilgit", "Gilgit")]


@pytest.mark.skipif(not HAS_SPACY_MODEL, reason="spaCy model en_core_web_sm not installed")
@pytest.mark.parametrize(
    "text, places",
    [
        ("Water bodies around Mangla Dam in 2023", ["Mangla Dam"]),
        ("land surface temperature of lahore for the last three summers", ["Lahore"]),
        ("ndvi over sahiwal and okara in 2022", ["Sahiwal", "Okara"]),
        ("MODIS NDVI of Punjab since 2020", ["Punjab"]),
    ],
)
def test_spacy_finds_places_including_lower_case(text, places):
    extractor = QueryEntityExtractor(today=TODAY)
    assert [v for _, v in found(extractor, text, "PLACE")] == places


def test_nothing_found_in_small_talk():
    assert RULES.extract("show me something nice") == []


def test_hints_list_each_entity_with_its_value():
    hints = format_entity_hints(RULES.extract("Sentinel-2 NDVI for Faisalabad in 2024"))
    assert 'DATASET: "Sentinel-2" -> sentinel2_sr' in hints
    assert 'PROCESS: "NDVI"' in hints and "-> NDVI" not in hints  # same as written: no arrow
    assert 'DATE: "in 2024" -> 2024-01-01/2024-12-31' in hints
    assert format_entity_hints([]) == ""


def test_offsets_point_at_the_text():
    text = "Sentinel-2 NDVI for Faisalabad from June to August 2024"
    for entity in RULES.extract(text):
        assert text[entity.start:entity.end] == entity.text
