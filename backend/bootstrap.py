"""Composition root: builds the backend object graph for the UI."""

from __future__ import annotations

from backend.business.facade import BusinessFacade, IBusinessFacade
from backend.business.request import RequestService


def build_business_facade() -> IBusinessFacade:
    request_service = RequestService()
    return BusinessFacade(request_service=request_service)
