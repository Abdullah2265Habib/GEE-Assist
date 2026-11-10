"""Splitting a gkonsol command line into words, and the words into options and arguments.

Rules (the same in every command):

* Words are separated by spaces. Quotes ("..." or '...') keep spaces inside one word:
  ``form set output "D:\\GEE data"``.
* A backslash is an ordinary character, so Windows paths need no escaping.
* ``--name value``, ``--name=value`` and ``-n value`` give an option a value;
  ``--flag`` / ``-f`` switch a flag on, and flags can be combined: ``-dy``.
* A negative number (``-73.5``) is an argument, not an option, so coordinates work.
* After ``--`` every word is an argument.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

_NUMBER = re.compile(r"^-(\d+(\.\d*)?|\.\d+)$")


class UsageError(Exception):
    """A command was typed wrongly: the message says what to fix."""


@dataclass(frozen=True)
class Option:
    name: str                       # long name without the dashes: "detach"
    help: str = ""
    short: str = ""                 # one letter: "d"
    value: str = ""                 # a name for its value ("MB") if it takes one; empty for a flag
    choices: tuple[str, ...] = ()   # allowed values, if limited

    @property
    def is_flag(self) -> bool:
        return not self.value

    def syntax(self) -> str:
        names = f"-{self.short}, --{self.name}" if self.short else f"    --{self.name}"
        return f"{names} {self.value}" if self.value else names


@dataclass
class Args:
    """What was typed after the command's name."""

    words: list[str] = field(default_factory=list)       # arguments, in order
    options: dict[str, Any] = field(default_factory=dict)  # option name -> True (flag) or its value
    raw: str = ""                                          # the rest of the line as typed

    def flag(self, name: str) -> bool:
        return bool(self.options.get(name))

    def value(self, name: str, default: Optional[str] = None) -> Optional[str]:
        value = self.options.get(name)
        return value if isinstance(value, str) else default

    def word(self, index: int, default: Optional[str] = None) -> Optional[str]:
        return self.words[index] if index < len(self.words) else default


def tokenize(text: str) -> list[str]:
    """The words of a command line; quotes group words, backslashes are kept as they are."""
    words: list[str] = []
    current: list[str] = []
    quote: Optional[str] = None
    started = False  # "" is a word too
    for char in text:
        if quote:
            if char == quote:
                quote = None
            else:
                current.append(char)
        elif char in "\"'":
            quote, started = char, True
        elif char.isspace():
            if started:
                words.append("".join(current))
                current, started = [], False
        else:
            current.append(char)
            started = True
    if quote:
        raise UsageError(f"The quote {quote} is not closed.")
    if started:
        words.append("".join(current))
    return words


def parse(words: list[str], options: list[Option]) -> Args:
    """Sort ``words`` into arguments and the given ``options``."""
    by_name = {option.name: option for option in options}
    by_letter = {option.short: option for option in options if option.short}
    args = Args()
    only_arguments = False
    i = 0
    while i < len(words):
        word = words[i]
        if only_arguments or not word.startswith("-") or word == "-" or _NUMBER.match(word):
            args.words.append(word)
        elif word == "--":
            only_arguments = True
        elif word.startswith("--"):
            name, has_value, value = word[2:].partition("=")
            option = by_name.get(name)
            if option is None:
                raise UsageError(f"Unknown option --{name}.")
            if option.is_flag:
                if has_value:
                    raise UsageError(f"--{name} does not take a value.")
                args.options[name] = True
            else:
                if not has_value:
                    i += 1
                    value = _next_value(words, i, f"--{name}", option)
                args.options[name] = _checked(value, f"--{name}", option)
        else:
            letters = word[1:]
            for position, letter in enumerate(letters):
                option = by_letter.get(letter)
                if option is None:
                    raise UsageError(f"Unknown option -{letter}.")
                if option.is_flag:
                    args.options[option.name] = True
                    continue
                value = letters[position + 1:]  # -n5
                if not value:
                    i += 1
                    value = _next_value(words, i, f"-{letter}", option)
                args.options[option.name] = _checked(value, f"-{letter}", option)
                break
        i += 1
    return args


def _next_value(words: list[str], i: int, spelled: str, option: Option) -> str:
    if i >= len(words):
        raise UsageError(f"{spelled} needs a value ({option.value}).")
    return words[i]


def _checked(value: str, spelled: str, option: Option) -> str:
    if option.choices and value not in option.choices:
        raise UsageError(f"{spelled} must be one of: {', '.join(option.choices)}.")
    return value
