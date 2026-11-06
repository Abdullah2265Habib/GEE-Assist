"""The account card and the sign-up details dialog (no window on screen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timezone  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication  # noqa: E402

from backend.business.facade import IBusinessFacade  # noqa: E402
from backend.dto.user_dto import UserDTO  # noqa: E402
from frontend.views.account_view import AccountView, SignupDetailsDialog, format_date  # noqa: E402

SIGNED_UP = datetime(2026, 3, 14, 9, 30, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _user(**extra) -> UserDTO:
    values = dict(id="1", username="ayesha", full_name="Ayesha Khan", role="user", email="ayesha@example.com",
                  email_verified=True, phone_number="+923001234567", auth_provider="local", created_at=SIGNED_UP)
    values.update(extra)
    return UserDTO(**values)


def test_signup_details_show_what_the_user_signed_up_with(app):
    dialog = SignupDetailsDialog(_user())
    shown = {key: label.text() for key, label in dialog.values.items()}

    assert shown == {
        "full_name": "Ayesha Khan",
        "username": "ayesha",
        "email": "ayesha@example.com  ✓ verified",
        "phone": "+923001234567",
        "provider": "Username and password",
        "created": format_date(SIGNED_UP),
    }
    dialog.deleteLater()


def test_signup_details_for_a_google_account_without_a_phone(app):
    dialog = SignupDetailsDialog(_user(auth_provider="google", phone_number=None, email_verified=False))

    assert dialog.values["provider"].text() == "Google"
    assert dialog.values["phone"].text() == "—"
    assert dialog.values["email"].text() == "ayesha@example.com  (not verified)"
    dialog.deleteLater()


def test_account_card_shows_the_same_details(app):
    card = AccountView(MagicMock(spec=IBusinessFacade))
    card.set_user(_user())

    assert card._values["email"].text() == "ayesha@example.com  ✓ verified"
    assert card._values["provider"].text() == "Username and password"
    card.deleteLater()
