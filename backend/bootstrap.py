"""Composition root: builds the backend object graph for the UI."""

from __future__ import annotations

from backend.business.download import Chunker, ChunkMerger, DownloadService
from backend.business.facade import BusinessFacade, IBusinessFacade
from backend.business.map import MapService
from backend.business.request import RequestService
from backend.business.user import UserService
from backend.config import DEFAULT_DOWNLOAD_DIR, DownloadSettingsStore
from backend.config.llm import load_llm_settings
from backend.config.settings import get_settings
from backend.data.clients.auth_api_client import AuthApiClient
from backend.data.clients.gee_client import GEEClient
from backend.data.clients.gemini_client import GeminiClient
from backend.data.clients.nominatim_client import NominatimClient
from backend.data.data_facade import DataFacade
from backend.data.session_store import KeyringSessionStore


def build_business_facade() -> IBusinessFacade:
    settings = get_settings()
    user_service = UserService(
        api=AuthApiClient(settings.auth_api_url, timeout=settings.auth_api_timeout),
        session_store=KeyringSessionStore(settings.keyring_service),
        session_duration=settings.session_duration,
    )

    llm = load_llm_settings()
    data_facade = DataFacade(
        gemini_client=GeminiClient(api_key=llm.api_key, model=llm.model),
        gee_client=GEEClient(project=settings.gee_project),
        geocoding_client=NominatimClient(),
    )
    request_service = RequestService(data_facade=data_facade)

    download_settings = DownloadSettingsStore()
    download_service = DownloadService(
        data_facade=data_facade,
        chunker=Chunker(download_settings),
        chunk_merger=ChunkMerger(),
        download_dir=DEFAULT_DOWNLOAD_DIR,
        retry_limit=download_settings.load().retry_limit,
        settings=download_settings,
    )

    return BusinessFacade(
        user_service=user_service,
        request_service=request_service,
        download_service=download_service,
        map_service=MapService(),
    )
