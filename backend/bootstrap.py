"""Composition root: builds the backend object graph for the UI."""

from __future__ import annotations

from backend.business.facade import BusinessFacade, IBusinessFacade
from backend.business.request import RequestService
from backend.config.llm import load_llm_settings
from backend.data.clients.gemini_client import GeminiClient
from backend.data.data_facade import DataFacade


def build_business_facade() -> IBusinessFacade:
    llm = load_llm_settings()
    data_facade = DataFacade(gemini_client=GeminiClient(api_key=llm.api_key, model=llm.model))
    request_service = RequestService(data_facade=data_facade)
    return BusinessFacade(request_service=request_service)
