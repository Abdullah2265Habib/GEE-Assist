from __future__ import annotations

from backend.business.facade.i_business_facade import IBusinessFacade
from backend.business.request.i_request_service import IRequestService
from backend.business.user.i_user_service import IUserService
from backend.dto import FormDTO, ValidationDTO
from backend.dto.user_dto import (
    GoogleSignInDTO,
    SignupDTO,
    SignupResultDTO,
    UserDTO,
    UserPageDTO,
    VerificationStatusDTO,
)


class BusinessFacade(IBusinessFacade):
    """Class diagram: BusinessFacade. Delegates to the services.

    Other services (download, analysis, map, explanation, report) are
    injected here as their use cases are implemented.
    """

    def __init__(self, user_service: IUserService, request_service: IRequestService):
        self._user_service = user_service
        self._request_service = request_service

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

    def import_aoi(self, file_path: str) -> str:
        return self._request_service.import_aoi(file_path)

    def get_kept_requests(self) -> list[FormDTO]:
        return self._request_service.get_kept_requests()
