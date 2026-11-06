from __future__ import annotations

from abc import ABC, abstractmethod

from backend.dto import DownloadJobDTO, FormDTO, ValidationDTO
from backend.dto.user_dto import (
    GoogleSignInDTO,
    SignupDTO,
    SignupResultDTO,
    UserDTO,
    UserPageDTO,
    VerificationStatusDTO,
)


class IBusinessFacade(ABC):
    """Class diagram: IBusinessFacade. The only backend entry point the UI uses.

    The authentication, query-input and download operations exist so far; the other
    use cases (analysis, maps, ...) add their methods here.
    """

    # ------------------------------------------------------------- authentication
    @abstractmethod
    def is_server_available(self) -> bool: ...

    @abstractmethod
    def get_current_user(self) -> UserDTO | None: ...

    @abstractmethod
    def log_in(self, username: str, password: str, remember: bool = False) -> UserDTO: ...

    @abstractmethod
    def restore_session(self) -> UserDTO | None: ...

    @abstractmethod
    def reload_current_user(self) -> UserDTO: ...

    @abstractmethod
    def log_out(self) -> None: ...

    @abstractmethod
    def sign_up(self, data: SignupDTO) -> SignupResultDTO: ...

    @abstractmethod
    def get_verification_status(self, verification_token: str) -> VerificationStatusDTO: ...

    @abstractmethod
    def resend_verification_email(self, verification_token: str, new_email: str | None = None) -> str: ...

    @abstractmethod
    def start_google_sign_in(self) -> GoogleSignInDTO: ...

    @abstractmethod
    def poll_google_sign_in(self, session_id: str, remember: bool = False) -> UserDTO | None: ...

    # ------------------------------------------------------------- user administration
    @abstractmethod
    def list_users(self, skip: int = 0, limit: int = 50) -> UserPageDTO: ...

    @abstractmethod
    def get_user(self, user_id: str) -> UserDTO: ...

    @abstractmethod
    def set_user_role(self, user_id: str, role: str) -> UserDTO: ...

    @abstractmethod
    def set_user_active(self, user_id: str, is_active: bool) -> UserDTO: ...

    # ------------------------------------------------------------- query input
    @abstractmethod
    def submit_query(self, text: str) -> FormDTO: ...

    @abstractmethod
    def submit_form(self, form: FormDTO) -> ValidationDTO: ...

    @abstractmethod
    def import_aoi(self, file_path: str) -> str: ...

    @abstractmethod
    def get_kept_requests(self) -> list[FormDTO]: ...

    # ------------------------------------------------------------- download (UC-05)
    @abstractmethod
    def start_download(self, form: FormDTO) -> DownloadJobDTO: ...

    @abstractmethod
    def get_download_progress(self, job: DownloadJobDTO) -> DownloadJobDTO: ...

    @abstractmethod
    def pause_download(self, job: DownloadJobDTO) -> DownloadJobDTO: ...

    @abstractmethod
    def resume_download(self, job: DownloadJobDTO) -> DownloadJobDTO: ...

    @abstractmethod
    def cancel_download(self, job: DownloadJobDTO) -> DownloadJobDTO: ...

    @abstractmethod
    def retry_failed_chunks(self, job: DownloadJobDTO) -> DownloadJobDTO: ...

    @abstractmethod
    def list_downloads(self) -> list[DownloadJobDTO]: ...

    @abstractmethod
    def get_chunk_size_mb(self) -> int: ...

    @abstractmethod
    def set_chunk_size_mb(self, size_mb: int) -> int: ...

    @abstractmethod
    def is_gee_available(self) -> bool: ...
