"""Helpers shared by gkonsol commands: typed values, datasets, confirmations, display."""

from datetime import date, datetime, timedelta, timezone

import pytest

from frontend.gkonsol.commands import common
from frontend.gkonsol.effects import Ask
from frontend.gkonsol.parser import UsageError


def test_confirm_asks_and_reads_the_answer():
    question = common.confirm("Sign out?")
    ask = next(question)
    assert ask == Ask("Sign out? [y/N]", default="n", choices=("y", "n"))
    with pytest.raises(StopIteration) as answer:
        question.send("Yes")
    assert answer.value.value is True


def test_confirm_with_yes_does_not_ask():
    question = common.confirm("Cancel the download?", assume_yes=True)
    with pytest.raises(StopIteration) as answer:
        next(question)
    assert answer.value.value is True


def test_confirm_defaulting_to_yes():
    assert next(common.confirm("Submit now?", default=True)).prompt == "Submit now? [Y/n]"


@pytest.mark.parametrize("word, current, expected", [
    (None, False, True), ("toggle", True, False), ("on", False, True), ("off", True, False),
    ("show", False, True), ("hide", True, False),
])
def test_switch(word, current, expected):
    assert common.switch(word, current) is expected


def test_switch_refuses_other_words():
    with pytest.raises(UsageError, match="on, off or toggle"):
        common.switch("maybe", False)


def test_numbers():
    assert common.to_int("1_000", "Scale") == 1000 and common.to_int("2,500", "Scale") == 2500
    assert common.to_float("-73.5", "West") == -73.5
    with pytest.raises(UsageError, match="whole number"):
        common.to_int("ten", "Scale")
    with pytest.raises(UsageError, match="from 0 to 100"):
        common.to_int("150", "Cloud cover", 0, 100)
    with pytest.raises(UsageError, match="from -180 to 180"):
        common.to_float("190", "West", -180, 180)


def test_dates():
    assert common.to_date("2024-06-01") == date(2024, 6, 1)
    with pytest.raises(UsageError, match="YYYY-MM-DD"):
        common.to_date("01/06/2024", "Start date")


@pytest.mark.parametrize("word, metres", [("500", 500), ("500m", 500), ("2.5km", 2500), ("3 KM", 3000)])
def test_distances(word, metres):
    assert common.to_metres(word) == metres


@pytest.mark.parametrize("word", ["0", "-5km", "far", "5 miles"])
def test_bad_distances(word):
    with pytest.raises(UsageError, match="distance"):
        common.to_metres(word)


@pytest.mark.parametrize("word, key", [
    ("sentinel2_sr", "sentinel2_sr"), ("Landsat-8", "landsat8_l2"), ("landsat 8", "landsat8_l2"),
    ("s2", "sentinel2_sr"), ("era5", "era5_land_daily"), ("dynamic", "dynamic_world"),
])
def test_datasets_are_found_by_key_name_or_start(word, key):
    assert common.find_dataset(word).key == key


def test_ambiguous_or_unknown_datasets_are_explained():
    with pytest.raises(UsageError, match="could be"):
        common.find_dataset("landsat")
    with pytest.raises(UsageError, match="datasets list"):
        common.find_dataset("spot6")


def test_when_shows_local_time():
    assert common.when(None) == "—"
    assert common.when(datetime(2026, 11, 10, 18, 33)) == "10 Nov 2026, 18:33"
    aware = datetime(2026, 11, 10, 13, 33, tzinfo=timezone.utc)
    assert common.when(aware) == aware.astimezone().strftime("%d %b %Y, %H:%M")


@pytest.mark.parametrize("seconds, text", [
    (None, "—"), (45, "45 s"), (720, "12 min"), (7500, "2 h 05 min"), (timedelta(days=6, hours=23).total_seconds(), "6 d 23 h"),
])
def test_duration(seconds, text):
    assert common.duration(seconds) == text


def test_timed_measures_the_call():
    result, milliseconds = common.timed(lambda a: a * 2, 21)
    assert result == 42 and milliseconds >= 0
