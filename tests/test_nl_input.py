"""UC-02 Enter Natural Language Query."""

from __future__ import annotations

import pytest

from backend.business.request import RequestService
from backend.config.limits import MAX_QUERY_LENGTH
from backend.exceptions import ValidationError


def test_query_is_kept_with_normalised_whitespace():
    service = RequestService()
    form = service.submit_query("  NDVI for   Faisalabad\n in 2024  ")
    assert form.source == "nl"
    assert form.query_text == "NDVI for Faisalabad in 2024"
    assert service.get_kept_requests() == [form]


@pytest.mark.parametrize("text", ["", "   ", "\n\t", None])
def test_empty_query_is_rejected(text):                      # alternate flow 5a
    service = RequestService()
    with pytest.raises(ValidationError):
        service.submit_query(text)
    assert service.get_kept_requests() == []


def test_too_long_query_is_rejected():
    with pytest.raises(ValidationError):
        RequestService().submit_query("a" * (MAX_QUERY_LENGTH + 1))
