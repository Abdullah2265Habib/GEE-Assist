"""Sign-up checks done in the app before calling the server.

They mirror the server's rules (GEE-Assist-Backend ``app/auth/signup/dto.py``), so the user sees
mistakes immediately. The server still validates everything again.
"""

from __future__ import annotations

import re

from backend.dto.user_dto import SignupDTO

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.]{3,30}$")
PHONE_PATTERN = re.compile(r"^\+[1-9][0-9]{9,14}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


def normalize_phone_number(value: str) -> str:
    normalized = re.sub(r"[\s\-()]", "", value)
    if normalized.startswith("00"):
        normalized = "+" + normalized[2:]
    return normalized


def normalize_full_name(value: str) -> str:
    return " ".join(value.split())


def validate_signup(data: SignupDTO, confirm_password: str) -> dict[str, str]:
    """Returns {field: message} for every invalid field (empty dict = valid)."""
    errors: dict[str, str] = {}

    name = normalize_full_name(data.full_name)
    if len(name) < 2:
        errors["full_name"] = "Enter your full name"
    elif len(name) > 100:
        errors["full_name"] = "Must be at most 100 characters"
    elif not all(part.replace("-", "").replace("'", "").isalpha() for part in name.split(" ")):
        errors["full_name"] = "Use letters, spaces, hyphens and apostrophes only"

    email = data.email.strip()
    if not email:
        errors["email"] = "Enter your email address"
    elif len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        errors["email"] = "Enter a valid email address, e.g. name@example.com"

    phone = normalize_phone_number(data.phone_number)
    if not phone:
        errors["phone_number"] = "Enter your phone number"
    elif not PHONE_PATTERN.fullmatch(phone):
        errors["phone_number"] = "Use international format with country code, e.g. +923001234567"

    username = data.username.strip()
    if not username:
        errors["username"] = "Choose a username"
    elif not USERNAME_PATTERN.fullmatch(username):
        errors["username"] = "3-30 characters: letters, digits, '_' or '.'"

    if not data.password.strip():
        errors["password"] = "Choose a password"
    elif len(data.password) < PASSWORD_MIN_LENGTH:
        errors["password"] = f"Must be at least {PASSWORD_MIN_LENGTH} characters"
    elif len(data.password) > PASSWORD_MAX_LENGTH:
        errors["password"] = f"Must be at most {PASSWORD_MAX_LENGTH} characters"

    if "password" not in errors and confirm_password != data.password:
        errors["confirm_password"] = "Passwords do not match"

    return errors


def clean_signup(data: SignupDTO) -> SignupDTO:
    """Same values, trimmed / normalised the way the server stores them."""
    return SignupDTO(
        full_name=normalize_full_name(data.full_name),
        email=data.email.strip().lower(),
        phone_number=normalize_phone_number(data.phone_number),
        username=data.username.strip().lower(),
        password=data.password,  # never altered
    )


def password_strength(password: str) -> int:
    """0 (empty) .. 4 (strong): a rough guide shown under the password field."""
    if not password:
        return 0
    score = 0
    if len(password) >= PASSWORD_MIN_LENGTH:
        score += 1
    if len(password) >= 12:
        score += 1
    if re.search(r"[a-z]", password) and re.search(r"[A-Z]", password):
        score += 1
    if re.search(r"\d", password) and re.search(r"[^A-Za-z0-9]", password):
        score += 1
    return max(1, score)
