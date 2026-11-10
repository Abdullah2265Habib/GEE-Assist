"""gkonsol's account commands: whoami, user, session, signout, users and server."""

from datetime import datetime, timedelta

import pytest

from backend.auth_exceptions import InvalidRequestError, NotFoundError, ServerUnavailableError, SessionExpiredError
from backend.dto.user_dto import SessionInfoDTO, UserPageDTO
from tests.gkonsol_fakes import terminal, user


@pytest.fixture
def term():
    return terminal()


@pytest.fixture
def admin():
    term = terminal(role="admin")
    people = [user("admin", username="ayesha"), user(id="u2", username="bilal", full_name="Bilal Ahmed"),
              user(id="u3", username="sara", full_name="Sara Ali", is_active=False)]
    term.facade.list_users.side_effect = lambda skip, limit: UserPageDTO(len(people), people[skip:skip + limit], skip, limit)
    return term


# ------------------------------------------------------------------ you
def test_whoami(term):
    assert term.type("whoami").endswith("ayesha  Ayesha Khan  ·  User")


def test_user_info_shows_the_details(term):
    printed = term.type("user")
    assert "Ayesha Khan  (ayesha)" in printed
    assert "ayesha@example.com  ✓ verified" in printed and "Username and password" in printed
    assert "'user info --refresh'" in printed


def test_user_info_refresh_loads_from_the_server(term):
    term.facade.reload_current_user.return_value = user(full_name="Ayesha K. Khan")
    printed = term.type("user info --refresh")
    assert "Ayesha K. Khan" in printed and "--refresh" not in printed.split("\n", 1)[1]


def test_an_expired_session_is_explained(term):
    term.facade.reload_current_user.side_effect = SessionExpiredError("expired", 401)
    printed = term.type("user info -r")
    assert "Your session has expired." in printed and "signout" in printed


def test_nobody_signed_in(term):
    term.facade.get_current_user.return_value = None
    assert "Nobody is signed in." in term.type("whoami")


# ------------------------------------------------------------------ session
def test_session_show_for_a_kept_session(term):
    until = (datetime.now() + timedelta(days=6, hours=23, minutes=30)).astimezone()
    term.facade.get_session_info.return_value = SessionInfoDTO(
        signed_in=True, remembered=True, saved_until=until, access_expires_in=1740, has_refresh_token=True)
    printed = term.type("session")
    assert "Kept signed in" in printed and "(in 6 d 23 h)" in printed
    assert "renews in 29 min" in printed and "Server" in printed and "held" in printed


def test_session_show_for_a_session_that_is_not_kept(term):
    term.facade.get_session_info.return_value = SessionInfoDTO(signed_in=True, remembered=False)
    assert "No: you sign in again when GEE-Assist starts" in term.type("session show")


def test_session_verify(term):
    term.facade.reload_current_user.return_value = user()
    printed = term.type("session verify")
    assert "✓ Your session is valid: the server accepted it" in printed and "ms)." in printed


@pytest.mark.parametrize("error, message", [
    (SessionExpiredError("expired", 401), "Your session has expired"),
    (ServerUnavailableError("Cannot reach the server."), "Cannot reach the server."),
])
def test_session_verify_failures(term, error, message):
    term.facade.reload_current_user.side_effect = error
    assert message in term.type("session check")


# ------------------------------------------------------------------ signout
def test_signout_asks_first(term):
    term.type("signout")
    assert term.shell.runner.asking.prompt == "Sign out of GEE-Assist? [y/N]"
    term.type("n")
    assert ("sign_out",) not in term.app.calls and "Still signed in." in term.output()
    term.type("logout")
    term.type("y")
    assert ("sign_out",) in term.app.calls


def test_signout_yes_does_not_ask(term):
    term.type("signout -y")
    assert term.app.calls == [("sign_out",)]


# ------------------------------------------------------------------ users
def test_users_list_is_a_table(admin):
    printed = admin.type("users")
    assert "USERNAME" in printed and "bilal" in printed and "disabled" in printed
    assert "Page 1 of 1  ·  3 users" in printed


def test_users_list_pages(admin):
    printed = admin.type("users list --size 2 -p 2")
    assert "sara" in printed and "bilal" not in printed and "Page 2 of 2" in printed


def test_users_are_for_administrators(term):
    assert "'users' is for administrators only." in term.type("users")


def test_users_show_finds_a_user_by_name(admin):
    printed = admin.type("users show Bilal")
    assert "Bilal Ahmed  (bilal)" in printed and "Active" in printed


def test_users_show_falls_back_to_the_id(admin):
    admin.facade.get_user.side_effect = NotFoundError("no", 404)
    assert "There is no user 'zed'" in admin.type("users show zed")


def test_users_role_asks_and_changes_it(admin):
    admin.facade.set_user_role.return_value = user(id="u2", username="bilal", role="admin")
    admin.type("users role bilal admin")
    assert admin.shell.runner.asking.prompt == "Make bilal an administrator? [y/N]"
    assert "✓ bilal is now an administrator." in admin.type("y")
    admin.facade.set_user_role.assert_called_once_with("u2", "admin")


def test_users_role_checks_the_role_and_the_current_one(admin):
    assert "The role is admin or user." in admin.type("users role bilal boss")
    assert "bilal is already a user." in admin.type("users role bilal user")


def test_server_refusals_are_shown(admin):
    admin.facade.set_user_role.side_effect = InvalidRequestError("You cannot change your own role.", 400)
    assert "You cannot change your own role." in admin.type("users role bilal admin -y")


def test_users_disable_asks_and_enable_does_not(admin):
    names = {"u2": "bilal", "u3": "sara"}
    admin.facade.set_user_active.side_effect = lambda user_id, active: user(id=user_id, username=names[user_id],
                                                                            is_active=active)
    admin.type("users disable bilal")
    assert "Disable bilal's account?" in admin.shell.runner.asking.prompt
    assert "bilal's account is disabled." in admin.type("y")
    assert "sara's account is already disabled." in admin.type("users disable sara")
    assert "sara's account is enabled." in admin.type("users enable sara")  # no question
    admin.facade.set_user_active.assert_called_with("u3", True)


def test_users_open_shows_the_window(admin):
    admin.type("users open")
    assert ("user_admin",) in admin.app.calls


def test_users_role_completes_the_role(admin):
    assert admin.shell.complete("users role bilal a")[1] == ["admin"]


# ------------------------------------------------------------------ server
def test_server_status(term):
    term.facade.is_server_available.return_value = True
    assert "is reachable" in term.type("server")
    term.facade.is_server_available.return_value = False
    printed = term.type("server ping")
    assert "Cannot reach the authentication server" in printed and "uvicorn" in printed
