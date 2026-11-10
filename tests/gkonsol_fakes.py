"""Test doubles for gkonsol: a scheduler the test drives, and a fake app and panel."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock

from backend.business.facade import IBusinessFacade
from backend.dto.user_dto import UserDTO
from frontend.gkonsol.command import Registry
from frontend.gkonsol.history import History
from frontend.gkonsol.output import BufferSink
from frontend.gkonsol.ports import MemoryForm
from frontend.gkonsol.shell import Shell


class StepScheduler:
    """Runs background tasks and timers only when the test says so."""

    def __init__(self):
        self.tasks, self.timers = [], []

    def run_task(self, fn, args, on_success, on_error):
        self.tasks.append((fn, args, on_success, on_error))

    def call_later(self, seconds, callback):
        self.timers.append((seconds, callback))

    def run_next(self):
        """Run the first waiting task and deliver its result."""
        fn, args, on_success, on_error = self.tasks.pop(0)
        try:
            result = fn(*args)
        except Exception as exc:
            on_error(exc)
        else:
            on_success(result)

    def finish_tasks(self):
        """Run the waiting tasks (and any they lead to), delivering their results."""
        while self.tasks:
            self.run_next()

    def fire_timers(self):
        timers, self.timers = self.timers, []
        for _, callback in timers:
            callback()

    def settle(self, rounds: int = 50):
        """Run tasks and timers until nothing is waiting (or ``rounds`` timer rounds)."""
        for _ in range(rounds):
            self.finish_tasks()
            if not self.timers:
                return
            self.fire_timers()
        self.finish_tasks()


@dataclass
class FakeApp:
    page: str = "dashboard"
    side_bar: bool = False
    full_screen: bool = False
    calls: list = field(default_factory=list)

    def current_page(self):
        return self.page

    def show_page(self, page):
        self.page = page
        self.calls.append(("show_page", page))

    def sign_out(self):
        self.calls.append(("sign_out",))

    def is_side_bar_expanded(self):
        return self.side_bar

    def set_side_bar_expanded(self, expanded):
        self.side_bar = expanded
        self.calls.append(("side_bar", expanded))

    def is_full_screen(self):
        return self.full_screen

    def set_full_screen(self, on):
        self.full_screen = on
        self.calls.append(("full_screen", on))

    def restart_with_theme(self, theme):
        self.calls.append(("theme", theme))

    def open_path(self, path):
        self.calls.append(("open_path", path))
        return True

    def open_url(self, url):
        self.calls.append(("open_url", url))
        return True

    def open_user_admin(self):
        self.calls.append(("user_admin",))

    def quit(self):
        self.calls.append(("quit",))


@dataclass
class FakePanel:
    maximized: bool = False
    pixels: int = 280
    closed: bool = False

    def is_terminal_maximized(self):
        return self.maximized

    def set_terminal_maximized(self, on):
        self.maximized = on

    def terminal_height(self):
        return self.pixels

    def set_terminal_height(self, pixels):
        self.pixels = pixels

    def hide_terminal(self):
        self.closed = True


def user(role: str = "user", **extra) -> UserDTO:
    values = dict(id="u1", username="ayesha", full_name="Ayesha Khan", role=role, email="ayesha@example.com",
                  email_verified=True)
    values.update(extra)
    return UserDTO(**values)


def facade(role: str = "user") -> MagicMock:
    fake = MagicMock(spec=IBusinessFacade)
    fake.get_current_user.return_value = user(role)
    fake.list_downloads.return_value = []
    fake.get_kept_requests.return_value = []
    fake.get_chunk_size_mb.return_value = 500
    return fake


@dataclass
class Terminal:
    """A shell with everything around it, for the tests."""

    shell: Shell
    sink: BufferSink
    scheduler: StepScheduler
    app: FakeApp
    panel: FakePanel
    facade: MagicMock

    @property
    def form(self):
        return self.shell.context.form

    def type(self, line: str, settle: bool = True) -> str:
        """Type ``line``, let background work finish, and return what was printed for it."""
        before = len(self.sink.lines)
        self.shell.submit(line)
        if settle:
            self.scheduler.settle()
        return "\n".join(self.output().split("\n")[before:])

    def output(self) -> str:
        return self.sink.text()


def terminal(registry: Registry | None = None, role: str = "user", columns: int = 100, fake=None) -> Terminal:
    """A terminal with every gkonsol command, or with ``registry``'s."""
    if registry is None:
        from frontend.gkonsol.commands import build_registry

        registry = build_registry()
    fake = fake or facade(role)
    sink, scheduler, app, panel = BufferSink(columns), StepScheduler(), FakeApp(), FakePanel()
    shell = Shell(registry, fake, app, MemoryForm(fake), panel, sink, scheduler, History())
    return Terminal(shell, sink, scheduler, app, panel, fake)
