"""gkonsol's shell: runs the lines typed in the terminal.

A typed line is shown after the prompt, kept in the history and run:

1. a ``!`` reference at its start is replaced from the history (``!!``, ``!3``, ``!gee``);
2. its first words name the command (``download start``);
3. the rest is split into options and arguments (``ask`` and ``echo`` get it as typed);
4. the command's handler runs. A handler that is a generator is driven by the runner
   until it ends, and lines typed meanwhile answer its questions.

Ctrl+C stops the running command. Tab completes command names, subcommands, options
and the values commands know about (datasets, bands, download ids...).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional

from backend.exceptions import GeeAssistError
from frontend.gkonsol import help as help_pages
from frontend.gkonsol import text
from frontend.gkonsol.command import Command, Registry
from frontend.gkonsol.effects import Sleep, Task
from frontend.gkonsol.history import History
from frontend.gkonsol.output import Sink, Writer
from frontend.gkonsol.parser import Args, UsageError, parse, tokenize
from frontend.gkonsol.ports import PAGES, AppPort, Context, FormPort, PanelPort
from frontend.gkonsol.runner import Runner, Scheduler
from frontend.gkonsol.text import Line, Span

logger = logging.getLogger(__name__)

# Words people type out of habit in other shells; gkonsol explains it is not one.
OTHER_SHELLS = {
    "cd", "dir", "ls", "pwd", "cat", "type", "copy", "del", "rm", "mkdir", "python", "pip", "git", "npm",
    "powershell", "cmd", "set", "export", "get-childitem", "set-location", "earthengine", "gcloud",
}


class Shell:
    def __init__(
        self,
        registry: Registry,
        facade: Any,
        app: AppPort,
        form: FormPort,
        panel: PanelPort,
        sink: Sink,
        scheduler: Scheduler,
        history: Optional[History] = None,
    ):
        self.registry = registry
        self.history = history or History()
        self.out = Writer(sink)
        self.context = Context(facade=facade, out=self.out, app=app, form=form, panel=panel, shell=self)
        self.runner = Runner(scheduler, self._finished, self._state_changed)
        self.on_state: Callable[[], None] = lambda: None  # the panel redraws the prompt line
        self._running: Optional[Command] = None

    # ------------------------------------------------------------- prompt and state
    def prompt(self) -> Line:
        """``ayesha@gkonsol ~/downloads $ `` — the user and the page the window shows."""
        user = self.context.user
        name = getattr(user, "username", None) or "guest"
        page = self.context.app.current_page()
        where = "~" if page == "dashboard" or page not in PAGES else f"~/{page}"
        return [Span(f"{name}@gkonsol", text.PROMPT_USER), Span(" "), Span(where, text.PROMPT_PATH), Span(" $ ")]

    @property
    def running(self) -> Optional[Command]:
        """The command that is running, if any."""
        return self._running if self.runner.running else None

    def status(self) -> str:
        """What the running command is doing, for the line under the output: "" when idle."""
        command = self.running
        if command is None or self.runner.asking is not None:
            return ""
        waiting = self.runner.waiting_for
        if isinstance(waiting, Task) and waiting.label:
            return f"{waiting.label}…  (Ctrl+C to stop)"
        if isinstance(waiting, Sleep):
            return f"{command.path} is running  (Ctrl+C to stop)"
        return f"{command.path}…  (Ctrl+C to stop)"

    # ------------------------------------------------------------- typed lines
    def submit(self, line: str) -> None:
        """A line typed in the terminal and Enter pressed."""
        question = self.runner.asking
        if question is not None:
            shown = "•" * len(line) if question.secret else line
            self.out.print(Span(question.prompt + " "), Span(shown, text.COMMAND))
            self.runner.answer(line if line.strip() else question.default)
            return
        if self.runner.running:
            self.out.muted("A command is still running. Press Ctrl+C to stop it.")
            return
        self.out.lines([self.prompt() + [Span(line, text.COMMAND)]])
        self.run_line(line)

    def run_line(self, line: str) -> None:
        """Run ``line`` as if it were typed: ``!`` references apply and it is kept in the history."""
        if not line.strip():
            return
        try:
            expanded = self.history.expand(line)
        except UsageError as exc:
            self.out.error(str(exc))
            return
        if expanded.strip() != line.strip():
            self.out.muted(expanded)  # show what the reference stood for, like other shells
        self.history.add(expanded)
        self.execute(expanded)

    def execute(self, line: str) -> None:
        """Run ``line`` without keeping it in the history."""
        words = line.split()
        if not words:
            return
        command, used = self.registry.resolve(words)
        if command is None:
            self._unknown(words[0])
            return
        if command.needs_admin() and not self.context.is_admin:
            self.out.error(f"'{command.path}' is for administrators only.")
            return
        rest = _after_words(line, used)
        next_word = rest.split()[0] if rest.split() else ""
        if command.subcommands and next_word and not next_word.startswith("-"):
            self.out.error(f"'{command.path}' has no subcommand '{next_word}'.")
            self.out.hint(f"help {command.path}  lists them")
            return
        if command.handler is None:
            self.out.lines(help_pages.command_help(command, self.context.is_admin))
            return
        self._running = command
        try:
            args = self._arguments(command, rest)
            result = command.handler(self.context, args)
        except Exception as exc:
            self._finished(exc, False)
            return
        self.runner.run(result)

    def interrupt(self) -> None:
        """Ctrl+C: stop the running command."""
        if self.runner.running:
            self.out.print(Span("^C", text.MUTED))
            self.runner.interrupt()

    def stop(self) -> None:
        """The terminal is closing for good: end the running command quietly."""
        self.runner.stop()
        self._running = None

    def clear(self) -> None:
        self.out.clear()

    # ------------------------------------------------------------- completion
    def complete(self, before_cursor: str) -> tuple[int, list[str]]:
        """Completions of the word ending at the cursor: (where that word starts, the candidates)."""
        start = len(before_cursor) - len(re.split(r"\s", before_cursor)[-1])
        prefix = before_cursor[start:]
        question = self.runner.asking
        if question is not None:
            return start, [choice for choice in question.choices if choice.startswith(prefix)]
        if self.runner.running:
            return start, []
        words = before_cursor[:start].split()
        is_admin = self.context.is_admin
        if not words:
            return start, _matching([c.names() for c in self.registry.commands(is_admin)], prefix)
        command, used = self.registry.resolve(words)
        if command is None or (command.needs_admin() and not is_admin):
            return start, []
        typed = words[used:]
        if command.subcommands and not typed and not prefix.startswith("-"):
            subs = [sub for sub in command.subcommands if is_admin or not sub.needs_admin()]
            return start, _matching([sub.names() for sub in subs], prefix)
        if prefix.startswith("-"):
            return start, [f"--{o.name}" for o in command.options if f"--{o.name}".startswith(prefix)]
        if command.completer is None:
            return start, []
        try:
            candidates = command.completer(self.context, typed, prefix)
        except Exception:
            logger.debug("Completion failed for %r", before_cursor, exc_info=True)
            return start, []
        return start, list(dict.fromkeys(c for c in candidates if c.startswith(prefix)))

    # ------------------------------------------------------------- helpers
    def _arguments(self, command: Command, rest: str) -> Args:
        if command.raw:
            return Args(raw=_unquote(rest.strip()))
        args = parse(tokenize(rest), command.options)
        args.raw = rest.strip()
        if len(args.words) < command.min_args:
            raise UsageError(f"'{command.path}' needs more arguments.")
        if command.max_args is not None and len(args.words) > command.max_args:
            extra = " ".join(args.words[command.max_args:])
            raise UsageError(f"Too many arguments for '{command.path}': {extra}")
        return args

    def _finished(self, error: Optional[BaseException], interrupted: bool) -> None:
        command, self._running = self._running, None
        if isinstance(error, UsageError):
            self.out.error(str(error))
            if command is not None:
                self.out.hint(f"Usage: {command.usage}   ·   help {command.path}")
        elif isinstance(error, GeeAssistError):
            self.out.error(str(error))
        elif error is not None:
            logger.error("gkonsol command failed", exc_info=error)
            self.out.error(f"Something went wrong: {type(error).__name__}: {error}")

    def _state_changed(self) -> None:
        self.on_state()

    def _unknown(self, word: str) -> None:
        self.out.error(f"'{word}' is not a gkonsol command.")
        suggestions = self.registry.suggest(word, self.context.is_admin)
        if suggestions:
            self.out.hint("Did you mean " + " or ".join(f"'{s}'" for s in suggestions) + "?")
        if word.lower() in OTHER_SHELLS:
            self.out.hint("gkonsol is GEE-Assist's own command line: Windows and PowerShell commands do not work here.")
            if word.lower() == "earthengine":
                self.out.hint("To sign in to Earth Engine, type: gee login")
        self.out.hint("Type 'help' to see every command.")


def _after_words(line: str, count: int) -> str:
    """What follows the first ``count`` words of ``line``, spacing kept."""
    if count == 0:
        return line
    matches = list(re.finditer(r"\S+", line))
    return line[matches[count - 1].end():] if len(matches) >= count else ""


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _matching(names: list[tuple[str, ...]], prefix: str) -> list[str]:
    """Names starting with ``prefix``; aliases only when no main name matches."""
    main = [group[0] for group in names if group[0].startswith(prefix)]
    if main:
        return main
    return [alias for group in names for alias in group[1:] if alias.startswith(prefix)]
