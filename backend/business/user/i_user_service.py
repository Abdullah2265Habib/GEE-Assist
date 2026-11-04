from __future__ import annotations

from abc import ABC, abstractmethod

from backend.dto.user_dto import (
    GoogleSignInDTO,
    SignupDTO,
    SignupResultDTO,
    UserDTO,
    UserPageDTO,
    VerificationStatusDTO,
)


class IUserService(ABC):
    """Class diagram: IUserService. Sign-up, sign-in, the current session and user administration.

    Methods talk to the network and block, so the UI calls them from a background worker.
    Failures raise ``backend.auth_exceptions.AuthError`` subclasses.
    """

    # ------------------------------------------------------------- server
    @abstractmethod
    def is_server_available(self) -> bool: ...

    # ------------------------------------------------------------- session
    @property
    @abstractmethod
    def current_user(self) -> UserDTO | None: ...

    @abstractmethod
    def log_in(self, username: str, password: str, remember: bool = False) -> UserDTO: ...

    @abstractmethod
    def restore_session(self) -> UserDTO | None:
        """Signs in with the refresh token saved by "Keep me signed in". None if there is none / it expired."""

    @abstractmethod
    def reload_current_user(self) -> UserDTO: ...

    @abstractmethod
    def log_out(self) -> None: ...

    # ------------------------------------------------------------- sign-up / verification
    @abstractmethod
    def sign_up(self, data: SignupDTO) -> SignupResultDTO: ...

    @abstractmethod
    def get_verification_status(self, verification_token: str) -> VerificationStatusDTO: ...

    @abstractmethod
    def resend_verification_email(self, verification_token: str, new_email: str | None = None) -> str: ...

    # ------------------------------------------------------------- Google
    @abstractmethod
    def start_google_sign_in(self) -> GoogleSignInDTO: ...

    @abstractmethod
    def poll_google_sign_in(self, session_id: str, remember: bool = False) -> UserDTO | None:
        """The signed-in user, or None while the user is still in the browser."""

    # ------------------------------------------------------------- admin
    @abstractmethod
    def list_users(self, skip: int = 0, limit: int = 50) -> UserPageDTO: ...

    @abstractmethod
    def get_user(self, user_id: str) -> UserDTO: ...

    @abstractmethod
    def set_user_role(self, user_id: str, role: str) -> UserDTO: ...

    @abstractmethod
    def set_user_active(self, user_id: str, is_active: bool) -> UserDTO: ...
