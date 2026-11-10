"""What gkonsol commands print to.

Commands print through a ``Writer``. It turns messages, tables and key/value pairs
into styled lines and hands them to a sink: the terminal view on screen, or
``BufferSink`` in the tests.

A ``Live`` region is a few lines at the bottom of the output that a command redraws
in place, like a progress bar. While one is shown, other output appears above it.
"""

from __future__ import annotations

from typing import Optional, Protocol, Sequence

from frontend.gkonsol import text as txt
from frontend.gkonsol.text import Line, Part, Span


class Sink(Protocol):
    columns: int  # characters that fit on a line

    def write(self, lines: list[Line]) -> None:
        """Add lines to the output (above the live region, if one is shown)."""

    def set_live(self, lines: list[Line]) -> None:
        """Show ``lines`` as the live region at the bottom, replacing what it showed."""

    def end_live(self, keep: bool) -> None:
        """The live region becomes ordinary output (``keep``) or is removed."""

    def clear(self) -> None:
        """Remove the output (a live region stays)."""


class Live:
    """Lines redrawn in place. ``done()`` leaves the last drawing in the output."""

    def __init__(self, sink: Sink):
        self._sink = sink
        self._finished = False

    def update(self, lines: list[Line]) -> None:
        if not self._finished:
            self._sink.set_live(lines)

    def done(self, keep: bool = True) -> None:
        if not self._finished:
            self._finished = True
            self._sink.end_live(keep)

    def __enter__(self) -> "Live":
        return self

    def __exit__(self, *exc: object) -> None:
        self.done()


class Writer:
    def __init__(self, sink: Sink):
        self._sink = sink

    @property
    def columns(self) -> int:
        return max(20, self._sink.columns)

    # ------------------------------------------------------------- lines
    def print(self, *parts: Part) -> None:
        self._sink.write([txt.line(*parts)])

    def lines(self, lines: Sequence[Line]) -> None:
        if lines:
            self._sink.write(list(lines))

    def blank(self) -> None:
        self._sink.write([[]])

    def text(self, value: str, style: str = txt.TEXT) -> None:
        self.lines(txt.styled(value, style))

    # ------------------------------------------------------------- messages
    def heading(self, value: str) -> None:
        self.print(Span(value, txt.HEADING))

    def muted(self, value: str) -> None:
        self.text(value, txt.MUTED)

    def info(self, value: str) -> None:
        self.text(value, txt.INFO)

    def success(self, value: str) -> None:
        self.print(Span(f"{txt.MARK_OK} ", txt.SUCCESS), Span(value, txt.SUCCESS))

    def warning(self, value: str) -> None:
        self.print(Span(f"{txt.MARK_WARN} ", txt.WARNING), Span(value, txt.WARNING))

    def error(self, value: str) -> None:
        self.print(Span(f"{txt.MARK_FAIL} ", txt.ERROR), Span(value, txt.ERROR))

    def hint(self, value: str) -> None:
        """A suggestion under a message: "  → run gee login"."""
        self.print(Span(f"  → {value}", txt.MUTED))

    # ------------------------------------------------------------- blocks
    def table(self, headers: Sequence[str], rows: Sequence[Sequence[object]], align: str = "",
              styles: Sequence[str] = ()) -> None:
        self.lines(txt.table(headers, rows, align, styles, max_width=self.columns))

    def pairs(self, pairs: Sequence[tuple[str, object]], value_style: str = txt.TEXT) -> None:
        self.lines(txt.key_values(pairs, value_style))

    def live(self) -> Live:
        return Live(self._sink)

    def clear(self) -> None:
        self._sink.clear()


class BufferSink:
    """Output kept in memory (the tests read it back as plain text)."""

    def __init__(self, columns: int = 100):
        self.columns = columns
        self.lines: list[Line] = []
        self.live: list[Line] = []

    def write(self, lines: list[Line]) -> None:
        self.lines.extend(list(line) for line in lines)

    def set_live(self, lines: list[Line]) -> None:
        self.live = [list(line) for line in lines]

    def end_live(self, keep: bool) -> None:
        if keep:
            self.lines.extend(self.live)
        self.live = []

    def clear(self) -> None:
        self.lines = []

    def text(self, live: Optional[bool] = True) -> str:
        shown = self.lines + (self.live if live else [])
        return "\n".join(txt.plain(line) for line in shown)
