from __future__ import annotations

from typing import Callable, Optional

from backend.business.download.i_download_service import IDownloadService
from backend.business.facade.i_business_facade import IBusinessFacade
from backend.business.map.i_map_service import IMapService
from backend.business.request.i_request_service import IRequestService
from backend.business.user.i_user_service import IUserService
from backend.dto import CheckDTO, DownloadJobDTO, FormDTO, PlaceDTO, ValidationDTO
from backend.dto.map_dto import RasterInfoDTO, RasterViewDTO, ViewPresetDTO
from backend.dto.user_dto import (
    GoogleSignInDTO,
    SessionInfoDTO,
    SignupDTO,
    SignupResultDTO,
    UserDTO,
    UserPageDTO,
    VerificationStatusDTO,
)


class BusinessFacade(IBusinessFacade):
    """Class diagram: BusinessFacade. Delegates to the services.

    Other services (analysis, explanation, report) are injected here as their use
    cases are implemented.
    """

    def __init__(
        self,
        user_service: IUserService,
        request_service: IRequestService,
        download_service: IDownloadService,
        map_service: IMapService,
    ):
        self._user_service = user_service
        self._request_service = request_service
        self._download_service = download_service
        self._map_service = map_service

    # ------------------------------------------------------------- authentication
    def is_server_available(self) -> bool:
        return self._user_service.is_server_available()

    def get_current_user(self) -> UserDTO | None:
        return self._user_service.current_user

    def log_in(self, username: str, password: str, remember: bool = False) -> UserDTO:
        return self._user_service.log_in(username, password, remember)

    def restore_session(self) -> UserDTO | None:
        return self._user_service.restore_session()

    def reload_current_user(self) -> UserDTO:
        return self._user_service.reload_current_user()

    def get_session_info(self) -> SessionInfoDTO:
        return self._user_service.get_session_info()

    def log_out(self) -> None:
        self._user_service.log_out()

    def sign_up(self, data: SignupDTO) -> SignupResultDTO:
        return self._user_service.sign_up(data)

    def get_verification_status(self, verification_token: str) -> VerificationStatusDTO:
        return self._user_service.get_verification_status(verification_token)

    def resend_verification_email(self, verification_token: str, new_email: str | None = None) -> str:
        return self._user_service.resend_verification_email(verification_token, new_email)

    def start_google_sign_in(self) -> GoogleSignInDTO:
        return self._user_service.start_google_sign_in()

    def poll_google_sign_in(self, session_id: str, remember: bool = False) -> UserDTO | None:
        return self._user_service.poll_google_sign_in(session_id, remember)

    # ------------------------------------------------------------- user administration
    def list_users(self, skip: int = 0, limit: int = 50) -> UserPageDTO:
        return self._user_service.list_users(skip, limit)

    def get_user(self, user_id: str) -> UserDTO:
        return self._user_service.get_user(user_id)

    def set_user_role(self, user_id: str, role: str) -> UserDTO:
        return self._user_service.set_user_role(user_id, role)

    def set_user_active(self, user_id: str, is_active: bool) -> UserDTO:
        return self._user_service.set_user_active(user_id, is_active)

    # ------------------------------------------------------------- query input
    def submit_query(self, text: str) -> FormDTO:
        return self._request_service.submit_query(text)

    def submit_form(self, form: FormDTO) -> ValidationDTO:
        return self._request_service.validate_form(form)

    def check_form(self, form: FormDTO) -> ValidationDTO:
        return self._request_service.check_form(form)

    def import_aoi(self, file_path: str) -> str:
        return self._request_service.import_aoi(file_path)

    def search_place(self, name: str) -> list[PlaceDTO]:
        return self._request_service.search_place(name)

    def get_kept_requests(self) -> list[FormDTO]:
        return self._request_service.get_kept_requests()

    # ------------------------------------------------------------- download (UC-05)
    def start_download(self, form: FormDTO) -> DownloadJobDTO:
        return self._download_service.start_download(form)

    def get_download_progress(self, job: DownloadJobDTO) -> DownloadJobDTO:
        return self._download_service.get_progress(job)

    def pause_download(self, job: DownloadJobDTO) -> DownloadJobDTO:
        return self._download_service.pause(job)

    def resume_download(self, job: DownloadJobDTO) -> DownloadJobDTO:
        return self._download_service.resume(job)

    def cancel_download(self, job: DownloadJobDTO) -> DownloadJobDTO:
        return self._download_service.cancel(job)

    def retry_failed_chunks(self, job: DownloadJobDTO) -> DownloadJobDTO:
        return self._download_service.retry_failed_chunks(job)

    def list_downloads(self) -> list[DownloadJobDTO]:
        return self._download_service.list_jobs()

    def get_chunk_size_mb(self) -> int:
        return self._download_service.chunk_size_mb()

    def set_chunk_size_mb(self, size_mb: int) -> int:
        return self._download_service.set_chunk_size_mb(size_mb)

    def is_gee_available(self) -> bool:
        return self._download_service.is_gee_available()

    def check_gee_setup(self) -> list[CheckDTO]:
        return self._download_service.check_gee_setup()

    def begin_gee_sign_in(self) -> str:
        return self._download_service.begin_gee_sign_in()

    def complete_gee_sign_in(self, should_stop: Optional[Callable[[], bool]] = None) -> str:
        return self._download_service.complete_gee_sign_in(should_stop)

    def cancel_gee_sign_in(self) -> None:
        self._download_service.cancel_gee_sign_in()

    def shutdown_downloads(self) -> None:
        self._download_service.shutdown()

    # ------------------------------------------------------------- viewing GeoTIFFs
    def describe_raster(self, path: str) -> RasterInfoDTO:
        return self._map_service.describe(path)

    def raster_view_presets(self, info: RasterInfoDTO) -> list[ViewPresetDTO]:
        return self._map_service.view_presets(info)

    def render_raster(self, info: RasterInfoDTO, preset: ViewPresetDTO, max_size: int = 1600) -> RasterViewDTO:
        return self._map_service.render(info, preset, max_size)

    def raster_values_at(self, info: RasterInfoDTO, lon: float, lat: float) -> dict[str, float | None]:
        return self._map_service.values_at(info, lon, lat)
