import pytest

from backend.config import settings
from backend.config.settings import parse_duration


@pytest.mark.parametrize(
    "text, seconds",
    [("90s", 90), ("2m", 120), ("12h", 43200), ("7d", 604800), ("7", 604800), (" 1.5H ", 5400)],
)
def test_parse_duration(text, seconds):
    assert parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["", "0m", "-1d", "5w", "two days"])
def test_parse_duration_rejects_invalid_text(text):
    with pytest.raises(ValueError):
        parse_duration(text)


def test_session_duration_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("SESSION_DURATION", "2m")
    assert settings._session_duration() == 120


def test_invalid_session_duration_falls_back_to_seven_days(monkeypatch):
    monkeypatch.setenv("SESSION_DURATION", "soon")
    assert settings._session_duration() == 7 * 24 * 3600
