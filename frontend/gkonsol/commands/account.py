"""Account commands: whoami, user, session, signout, users (administrators) and server."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generator

from backend.auth_exceptions import NotFoundError, ServerUnavailableError, SessionExpiredError
from backend.config.settings import get_settings
from backend.dto.user_dto import UserDTO
from frontend.gkonsol import text
from frontend.gkonsol.command import Command, Registry
from frontend.gkonsol.commands.common import YES, confirm, duration, timed, to_int, when
from frontend.gkonsol.effects import task
from frontend.gkonsol.parser import Args, Option, UsageError
from frontend.gkonsol.ports import Context
from frontend.gkonsol.text import Span

GROUP = "Account"
PROVIDERS = {"local": "Username and password", "google": "Google"}
USERS_PER_PAGE = 20
SEARCH_PAGE = 100     # users fetched at a time when looking a user up by name
SEARCH_PAGES = 20


# ----------------------------------------------------------------------------- you
def _signed_in(ctx: Context) -> UserDTO:
    user = ctx.user
    if user is None:
        raise UsageError("Nobody is signed in.")
    return user


def _whoami(ctx: Context, args: Args) -> None:
    user = _signed_in(ctx)
    ctx.out.print(Span(user.username, text.ACCENT), f"  {user.full_name}  ·  ", _role(user))


def _role(user: UserDTO) -> Span:
    return Span("Administrator", text.WARNING) if user.is_admin else Span("User")


def user_details(user: UserDTO) -> list[tuple[str, Any]]:
    email = user.email or "—"
    if user.email:
        email += "  ✓ verified" if user.email_verified else "  (not verified)"
    return [
        ("Email", email),
        ("Phone", user.phone_number or "—"),
        ("Role", _role(user)),
        ("Account", Span("Active", text.SUCCESS) if user.is_active else Span("Disabled", text.ERROR)),
        ("Sign-in method", PROVIDERS.get(user.auth_provider, user.auth_provider.title())),
        ("Member since", when(user.created_at)),
        ("Last sign-in", when(user.last_login_at)),
        ("User ID", user.id),
    ]


def _user_info(ctx: Context, args: Args) -> Generator:
    user = _signed_in(ctx)
    if args.flag("refresh"):
        try:
            user = yield task(ctx.facade.reload_current_user, label="Loading your details from the server")
        except SessionExpiredError:
            ctx.out.error("Your session has expired.")
            ctx.out.hint("Sign in again: signout")
            return
    ctx.out.print(Span(user.full_name, text.HEADING), Span(f"  ({user.username})", text.MUTED))
    ctx.out.pairs(user_details(user))
    if not args.flag("refresh"):
        ctx.out.muted("Shown as at sign-in; 'user info --refresh' loads them from the server.")


# ----------------------------------------------------------------------------- session
def _session_show(ctx: Context, args: Args) -> None:
    info = ctx.facade.get_session_info()
    if not info.signed_in:
        ctx.out.warning("Nobody is signed in.")
        return
    user = _signed_in(ctx)
    if info.remembered and info.saved_until is not None:
        left = (info.saved_until - datetime.now(info.saved_until.tzinfo)).total_seconds()
        kept = Span(f"Yes, until {when(info.saved_until)} (in {duration(left)})", text.SUCCESS)
    elif info.remembered:
        kept = Span("Yes", text.SUCCESS)
    else:
        kept = Span("No: you sign in again when GEE-Assist starts")
    ctx.out.pairs([
        ("Signed in as", f"{user.username} ({user.full_name})"),
        ("Server", get_settings().auth_api_url),
        ("Kept signed in", kept),
        ("Access token", f"renews in {duration(info.access_expires_in)}" if info.access_expires_in is not None
         else "—"),
        ("Refresh token", "held" if info.has_refresh_token else "none"),
    ])
    ctx.out.muted("'session verify' asks the server whether the session is still valid.")


def _session_verify(ctx: Context, args: Args) -> Generator:
    try:
        user, elapsed = yield task(timed, ctx.facade.reload_current_user, label="Checking your session with the server")
    except SessionExpiredError:
        ctx.out.error("Your session has expired: the server no longer accepts it.")
        ctx.out.hint("Sign in again: signout")
        return
    except ServerUnavailableError as exc:
        ctx.out.error(str(exc))
        ctx.out.hint("'server status' checks the connection")
        return
    ctx.out.success(f"Your session is valid: the server accepted it ({elapsed:.0f} ms).")
    ctx.out.pairs([("Signed in as", f"{user.username} ({user.full_name})"), ("Role", _role(user))])


def _sign_out(ctx: Context, args: Args) -> Generator:
    _signed_in(ctx)
    if not (yield from confirm("Sign out of GEE-Assist?", args.flag("yes"))):
        ctx.out.muted("Still signed in.")
        return
    ctx.out.muted("Signing out…")
    ctx.app.sign_out()


# ----------------------------------------------------------------------------- users (administrators)
def _users_list(ctx: Context, args: Args) -> Generator:
    page_number = to_int(args.value("page", "1"), "The page", 1, 100_000)
    size = to_int(args.value("size", str(USERS_PER_PAGE)), "The page size", 1, 100)
    page = yield task(ctx.facade.list_users, (page_number - 1) * size, size, label="Loading users")
    if not page.items:
        ctx.out.muted("No users on this page.")
        return
    rows = [
        [user.username, user.full_name, user.email or "—", user.role,
         "active" if user.is_active else "disabled", when(user.last_login_at)]
        for user in page.items
    ]
    ctx.out.table(["USERNAME", "NAME", "EMAIL", "ROLE", "ACCOUNT", "LAST SIGN-IN"], rows,
                  styles=(text.ACCENT, text.TEXT, text.TEXT, text.TEXT, text.TEXT, text.MUTED))
    ctx.out.muted(f"Page {page.page} of {page.page_count}  ·  {page.total} user{'s' if page.total != 1 else ''}")


def find_user(ctx: Context, key: str) -> Generator[Any, Any, UserDTO]:
    """A user by username (or the start of one) or id."""
    wanted = key.strip().lower()
    for number in range(SEARCH_PAGES):
        page = yield task(ctx.facade.list_users, number * SEARCH_PAGE, SEARCH_PAGE, label="Looking the user up")
        for user in page.items:
            if user.username.lower() == wanted or user.id == key:
                return user
        if (number + 1) * SEARCH_PAGE >= page.total:
            break
    try:
        return (yield task(ctx.facade.get_user, key, label="Looking the user up"))
    except NotFoundError:
        raise UsageError(f"There is no user '{key}'. 'users list' shows them.") from None


def _users_show(ctx: Context, args: Args) -> Generator:
    user = yield from find_user(ctx, args.words[0])
    ctx.out.print(Span(user.full_name, text.HEADING), Span(f"  ({user.username})", text.MUTED))
    ctx.out.pairs(user_details(user))


def _users_role(ctx: Context, args: Args) -> Generator:
    role = args.words[1].lower()
    if role not in ("admin", "user"):
        raise UsageError("The role is admin or user.")
    user = yield from find_user(ctx, args.words[0])
    if user.role == role:
        ctx.out.muted(f"{user.username} is already {'an administrator' if role == 'admin' else 'a user'}.")
        return
    label = "an administrator" if role == "admin" else "an ordinary user"
    if not (yield from confirm(f"Make {user.username} {label}?", args.flag("yes"))):
        ctx.out.muted("Nothing changed.")
        return
    changed = yield task(ctx.facade.set_user_role, user.id, role, label="Changing the role")
    ctx.out.success(f"{changed.username} is now {label}.")


def _set_active(active: bool):
    def handler(ctx: Context, args: Args) -> Generator:
        user = yield from find_user(ctx, args.words[0])
        if user.is_active == active:
            ctx.out.muted(f"{user.username}'s account is already {'enabled' if active else 'disabled'}.")
            return
        if not active and not (yield from confirm(f"Disable {user.username}'s account? They cannot sign in "
                                                  "until it is enabled again.", args.flag("yes"))):
            ctx.out.muted("Nothing changed.")
            return
        changed = yield task(ctx.facade.set_user_active, user.id, active,
                             label="Enabling the account" if active else "Disabling the account")
        ctx.out.success(f"{changed.username}'s account is {'enabled' if active else 'disabled'}.")
    return handler


def _users_open(ctx: Context, args: Args) -> None:
    ctx.app.open_user_admin()
    ctx.out.muted("The Manage users window is open.")


def _complete_role(ctx: Context, typed: list[str], prefix: str) -> list[str]:
    return ["admin", "user"] if len(typed) == 1 else []


# ----------------------------------------------------------------------------- server
def _server_status(ctx: Context, args: Args) -> Generator:
    url = get_settings().auth_api_url
    available, elapsed = yield task(timed, ctx.facade.is_server_available, label=f"Contacting {url}")
    if available:
        ctx.out.success(f"The authentication server at {url} is reachable ({elapsed:.0f} ms).")
    else:
        ctx.out.error(f"Cannot reach the authentication server at {url}.")
        ctx.out.hint("Start GEE-Assist-Backend (uvicorn app.main:app), or set AUTH_API_URL in .env.")


def register(registry: Registry) -> None:
    registry.add(Command("whoami", "Show who is signed in", _whoami, group=GROUP))

    user = registry.add(Command(
        "user", "Your account details", _user_info, aliases=("account",), group=GROUP,
        options=[Option("refresh", "Load them from the server first", short="r")],
        description="'user' alone is 'user info'.",
    ))
    user.add(Command(
        "info", "Show your name, email, role and sign-in dates", _user_info,
        options=[Option("refresh", "Load them from the server first", short="r")],
        examples=[("user info", "As they were at sign-in"), ("user info --refresh", "Fresh from the server")],
    ))

    session = registry.add(Command(
        "session", "Your sign-in session", _session_show, group=GROUP, description="'session' alone is 'session show'.",
    ))
    session.add(Command("show", "Whether you stay signed in, and until when", _session_show))
    session.add(Command(
        "verify", "Ask the server whether your session is still valid", _session_verify, aliases=("check",),
        description="Sends your access token to the authentication server (renewing it first if needed).",
    ))

    registry.add(Command(
        "signout", "Sign out of GEE-Assist", _sign_out, aliases=("logout",), group=GROUP, options=[YES],
        description="Asks first; -y signs out at once. The sign-in screen opens and a saved session is forgotten.",
        examples=[("signout", "Asks, then signs out"), ("signout -y", "Signs out without asking")],
    ))

    users = registry.add(Command(
        "users", "Manage user accounts (administrators)", _users_list, admin=True, group=GROUP,
        options=[Option("page", "Page number", short="p", value="N"), Option("size", "Users per page", value="N")],
        description="'users' alone is 'users list'. USER is a username or a user id.",
    ))
    users.add(Command(
        "list", "List the users, a page at a time", _users_list, aliases=("ls",),
        options=[Option("page", "Page number", short="p", value="N"), Option("size", "Users per page (1-100)", value="N")],
        examples=[("users list", "The first 20 users"), ("users list -p 2", "The next 20")],
    ))
    users.add(Command("show", "Show one user's details", _users_show, params="USER", min_args=1, max_args=1))
    users.add(Command(
        "role", "Make a user an administrator or an ordinary user", _users_role, params="USER admin|user",
        min_args=2, max_args=2, options=[YES], completer=_complete_role,
        examples=[("users role bilal admin", "Bilal becomes an administrator")],
    ))
    users.add(Command("enable", "Let a disabled user sign in again", _set_active(True), params="USER",
                      min_args=1, max_args=1))
    users.add(Command("disable", "Stop a user from signing in", _set_active(False), params="USER",
                      min_args=1, max_args=1, options=[YES]))
    users.add(Command("open", "Open the Manage users window", _users_open))

    server = registry.add(Command(
        "server", "The authentication server", _server_status, group=GROUP,
        description="'server' alone is 'server status'. The address is AUTH_API_URL in .env.",
    ))
    server.add(Command("status", "Check that the authentication server answers", _server_status, aliases=("ping",)))
