"""Composition root: builds the backend object graph for the UI."""

from __future__ import annotations

from backend.business.facade import BusinessFacade, IBusinessFacade
from backend.business.user import UserService
from backend.config.settings import get_settings
from backend.data.clients.auth_api_client import AuthApiClient
from backend.data.session_store import KeyringSessionStore


def build_business_facade() -> IBusinessFacade:
    settings = get_settings()
    user_service = UserService(
        api=AuthApiClient(settings.auth_api_url, timeout=settings.auth_api_timeout),
        session_store=KeyringSessionStore(settings.keyring_service),
    )
    return BusinessFacade(user_service=user_service)
