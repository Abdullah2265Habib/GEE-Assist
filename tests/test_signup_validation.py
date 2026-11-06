import pytest

from backend.business.user.signup_validation import clean_signup, password_strength, validate_signup
from backend.dto.user_dto import SignupDTO

VALID = dict(full_name="Abdullah Habib", email="abdullah@example.com", phone_number="+92 300 123-4567",
             username="abdullah", password="StrongPass123")


def _signup(**changes) -> SignupDTO:
    return SignupDTO(**{**VALID, **changes})


def test_valid_signup_has_no_errors():
    assert validate_signup(_signup(), "StrongPass123") == {}


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"full_name": "A"}, "full_name"),
        ({"full_name": "R2 D2"}, "full_name"),
        ({"email": "not-an-email"}, "email"),
        ({"phone_number": "03001234567"}, "phone_number"),
        ({"phone_number": "+92 300"}, "phone_number"),
        ({"username": "ab"}, "username"),
        ({"username": "bad name!"}, "username"),
        ({"password": "short"}, "password"),
        ({"password": "        "}, "password"),
    ],
)
def test_invalid_fields(changes, field):
    data = _signup(**changes)
    assert field in validate_signup(data, data.password)


def test_passwords_must_match():
    assert validate_signup(_signup(), "Different123") == {"confirm_password": "Passwords do not match"}


def test_phone_with_00_prefix_is_accepted():
    assert validate_signup(_signup(phone_number="00923001234567"), "StrongPass123") == {}


def test_clean_signup_normalises_like_the_server():
    cleaned = clean_signup(_signup(full_name="  Abdullah   Habib ", email=" A@Example.COM ", username=" Abdullah "))
    assert cleaned.full_name == "Abdullah Habib"
    assert cleaned.email == "a@example.com"
    assert cleaned.phone_number == "+923001234567"
    assert cleaned.username == "abdullah"
    assert cleaned.password == "StrongPass123"


def test_password_strength_grows():
    assert password_strength("") == 0
    assert password_strength("abc") == 1
    assert password_strength("Abcdefgh12!?xyz") == 4
