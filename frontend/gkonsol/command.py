"""gkonsol command definitions and the registry that finds them.

A command has a name, a one-line summary and a handler. It can have subcommands
(``download start``, ``download pause``...), options, aliases and examples; ``help``
and Tab completion read all of it from here, so a command is described in one place.

A handler is called as ``handler(context, args)``. It either does its work and
returns, or is a generator that yields effects (see ``effects``) to wait for a
background task, a pause or an answer from the user.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

from frontend.gkonsol.parser import Args, Option

Handler = Callable[[Any, Args], Any]
# (context, the arguments typed so far, the word being completed) -> candidates
Completer = Callable[[Any, list[str], str], list[str]]


@dataclass(eq=False)
class Command:
    name: str
    summary: str
    handler: Optional[Handler] = None
    params: str = ""                  # the arguments in the usage line, e.g. "[REQUEST]" or "<FIELD> <VALUE>..."
    description: str = ""             # more about the command, shown by "help <command>"
    options: list[Option] = field(default_factory=list)
    examples: list[tuple[str, str]] = field(default_factory=list)  # (command line, what it does)
    aliases: tuple[str, ...] = ()
    group: str = ""                   # the section "help" lists a top-level command in
    admin: bool = False               # administrators only
    raw: bool = False                 # gets the rest of the line as typed, quotes and all (ask, echo)
    min_args: int = 0
    max_args: Optional[int] = 0       # None: any number of arguments
    completer: Optional[Completer] = None
    subcommands: list["Command"] = field(default_factory=list)
    parent: Optional["Command"] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        for sub in self.subcommands:
            sub.parent = self

    @property
    def path(self) -> str:
        """The words that run it: "download start"."""
        return f"{self.parent.path} {self.name}" if self.parent else self.name

    @property
    def usage(self) -> str:
        parts = [self.path]
        if self.subcommands:
            parts.append("[subcommand]" if self.handler else "<subcommand>")
        if self.params:
            parts.append(self.params)
        if self.options:
            parts.append("[options]")
        return " ".join(parts)

    def names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)

    def add(self, sub: "Command") -> "Command":
        if any(name in other.names() for other in self.subcommands for name in sub.names()):
            raise ValueError(f"'{self.path}' already has a subcommand named {sub.names()}")
        sub.parent = self
        self.subcommands.append(sub)
        return sub

    def subcommand(self, word: str) -> Optional["Command"]:
        return next((sub for sub in self.subcommands if word in sub.names()), None)

    def needs_admin(self) -> bool:
        """True if this command or one it belongs to is for administrators only."""
        return self.admin or (self.parent is not None and self.parent.needs_admin())

    def walk(self) -> Iterator["Command"]:
        yield self
        for sub in self.subcommands:
            yield from sub.walk()


class Registry:
    """The top-level commands, in the order ``help`` lists them."""

    def __init__(self) -> None:
        self._commands: list[Command] = []

    def add(self, command: Command) -> Command:
        taken = {name for existing in self._commands for name in existing.names()}
        clash = taken.intersection(command.names())
        if clash:
            raise ValueError(f"gkonsol already has a command named {', '.join(sorted(clash))}")
        self._commands.append(command)
        return command

    def find(self, word: str) -> Optional[Command]:
        return next((command for command in self._commands if word in command.names()), None)

    def commands(self, is_admin: bool = True) -> list[Command]:
        return [command for command in self._commands if is_admin or not command.admin]

    def walk(self) -> Iterator[Command]:
        for command in self._commands:
            yield from command.walk()

    def resolve(self, words: list[str]) -> tuple[Optional[Command], int]:
        """The deepest command the first ``words`` name, and how many words that took."""
        command = self.find(words[0]) if words else None
        if command is None:
            return None, 0
        used = 1
        while used < len(words):
            sub = command.subcommand(words[used])
            if sub is None:
                break
            command, used = sub, used + 1
        return command, used

    def groups(self, is_admin: bool = True) -> dict[str, list[Command]]:
        grouped: dict[str, list[Command]] = {}
        for command in self.commands(is_admin):
            grouped.setdefault(command.group or "Other", []).append(command)
        return grouped

    def names(self, is_admin: bool = True) -> list[str]:
        return [name for command in self.commands(is_admin) for name in command.names()]

    def suggest(self, word: str, is_admin: bool = True) -> list[str]:
        """Command names that look like a mistyped ``word``."""
        return difflib.get_close_matches(word, self.names(is_admin), n=3, cutoff=0.6)
