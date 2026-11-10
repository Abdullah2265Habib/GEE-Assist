"""What a running gkonsol command can wait for.

A command that takes time is a generator. It yields an effect and is resumed with the
result once the effect is over, so the terminal stays responsive meanwhile:

    def verify(ctx, args):
        checks = yield Task(ctx.facade.check_gee_setup, label="Checking Earth Engine")
        answer = yield Ask("Sign in now? [Y/n]")
        yield Sleep(0.5)

* ``Task``  runs a blocking function (a network request) on a background thread and
            resumes the command with its return value; if it raises, the exception is
            raised at the ``yield``.
* ``Sleep`` resumes the command after some seconds (used to redraw live progress).
* ``Ask``   shows a question in place of the prompt and resumes the command with the
            line the user types.

Ctrl+C raises ``Interrupted`` at the ``yield``; a command can catch it to say what it
stopped, or let it end the command.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


class Interrupted(Exception):
    """The user pressed Ctrl+C while the command was waiting."""


@dataclass(frozen=True)
class Task:
    fn: Callable[..., Any]
    args: tuple = ()
    label: str = ""      # what is being waited for, shown while it runs: "Contacting Earth Engine"


def task(fn: Callable[..., Any], *args: Any, label: str = "") -> Task:
    """``yield task(facade.get_user, user_id, label="Loading the user")``."""
    return Task(fn, args, label)


@dataclass(frozen=True)
class Sleep:
    seconds: float


@dataclass(frozen=True)
class Ask:
    prompt: str                      # e.g. "Sign out of GEE-Assist? [y/N]"
    default: str = ""                # the answer when the user just presses Enter
    secret: bool = False             # hide what is typed
    choices: tuple[str, ...] = ()    # offered by Tab
