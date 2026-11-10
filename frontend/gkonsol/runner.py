"""Runs gkonsol commands one at a time and delivers what they wait for.

The runner does not use Qt itself: a scheduler runs background tasks and timers. The
terminal panel gives it one built on the app's worker pool and ``QTimer``; the tests
give it one they control step by step.

Every wait gets a number. A task or timer that ends after the command stopped waiting
for it (Ctrl+C) still calls back, but with an old number, and is ignored.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Optional, Protocol, Union

from frontend.gkonsol.effects import Ask, Interrupted, Sleep, Task

Effect = Union[Task, Sleep, Ask]


class Scheduler(Protocol):
    def run_task(self, fn: Callable[..., Any], args: tuple, on_success: Callable[[Any], None],
                 on_error: Callable[[BaseException], None]) -> None:
        """Run ``fn(*args)`` off the UI thread; call back on the UI thread."""

    def call_later(self, seconds: float, callback: Callable[[], None]) -> None:
        """Call ``callback`` on the UI thread after ``seconds``."""


class Runner:
    def __init__(
        self,
        scheduler: Scheduler,
        on_finished: Callable[[Optional[BaseException], bool], None],
        on_state: Callable[[], None] = lambda: None,
    ):
        """``on_finished(error, interrupted)`` is called when a command ends; ``on_state`` whenever
        what it waits for changes (the panel shows a spinner or the question)."""
        self._scheduler = scheduler
        self._on_finished = on_finished
        self._on_state = on_state
        self._command: Any = None           # the running generator
        self._wait = 0                      # number of the current wait
        self.waiting_for: Optional[Effect] = None

    # ------------------------------------------------------------- state
    @property
    def running(self) -> bool:
        return self._command is not None

    @property
    def asking(self) -> Optional[Ask]:
        return self.waiting_for if isinstance(self.waiting_for, Ask) else None

    # ------------------------------------------------------------- control
    def run(self, result: Any) -> None:
        """Run what a command's handler returned: a generator is driven to its end."""
        if not inspect.isgenerator(result):
            self._on_finished(None, False)
            return
        self._command = result
        self._advance(lambda: result.send(None))

    def answer(self, text: str) -> bool:
        """The user's answer to the question the command asked. False if it asked none."""
        if self.asking is None:
            return False
        self._resume(self._wait, value=text)
        return True

    def interrupt(self) -> bool:
        """Ctrl+C: raise ``Interrupted`` in the command. False if no command is running."""
        if self._command is None:
            return False
        self._wait += 1  # what it waited for no longer matters
        command = self._command
        self._advance(lambda: command.throw(Interrupted()))
        return True

    def stop(self) -> None:
        """End the running command at once (the terminal is closing). Its ``finally`` blocks run."""
        if self._command is None:
            return
        self._wait += 1
        command, self._command = self._command, None
        self.waiting_for = None
        command.close()

    # ------------------------------------------------------------- driving the generator
    def _advance(self, step: Callable[[], Any]) -> None:
        self.waiting_for = None
        try:
            effect = step()
        except StopIteration:
            self._end(None, False)
        except Interrupted:
            self._end(None, True)
        except Exception as exc:  # reported by the shell
            self._end(exc, False)
        else:
            self._wait_for(effect)

    def _wait_for(self, effect: Any) -> None:
        self._wait += 1
        wait = self._wait
        if not isinstance(effect, (Task, Sleep, Ask)):
            command = self._command
            self._advance(lambda: command.throw(TypeError(f"A command cannot wait for {effect!r}.")))
            return
        self.waiting_for = effect
        self._on_state()
        if isinstance(effect, Task):
            self._scheduler.run_task(
                effect.fn, effect.args,
                lambda result: self._resume(wait, value=result),
                lambda error: self._resume(wait, error=error),
            )
        elif isinstance(effect, Sleep):
            self._scheduler.call_later(effect.seconds, lambda: self._resume(wait))

    def _resume(self, wait: int, value: Any = None, error: Optional[BaseException] = None) -> None:
        if wait != self._wait or self._command is None:
            return  # a task or timer the command no longer waits for
        command = self._command
        if error is not None:
            self._advance(lambda: command.throw(error))
        else:
            self._advance(lambda: command.send(value))

    def _end(self, error: Optional[BaseException], interrupted: bool) -> None:
        self._command = None
        self.waiting_for = None
        self._on_finished(error, interrupted)
        self._on_state()
