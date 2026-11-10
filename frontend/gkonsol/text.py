"""Styled terminal text, and pictures drawn with characters.

A line is a list of spans; a span is some text in a named style. The terminal view
gives each style its colour from the theme, so commands never name colours.

The drawings (progress bar, sparkline, bar chart, table) are plain functions, so they
can be tested without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence, Union

# ----------------------------------------------------------------------------- styles
TEXT = "text"
MUTED = "muted"
BOLD = "bold"
ACCENT = "accent"        # green: names, highlights, progress
INFO = "info"            # blue: values, paths, links
SUCCESS = "success"
WARNING = "warning"
ERROR = "error"
HEADING = "heading"
COMMAND = "command"      # a command line the user typed
PROMPT_USER = "prompt-user"
PROMPT_PATH = "prompt-path"

STYLES = (TEXT, MUTED, BOLD, ACCENT, INFO, SUCCESS, WARNING, ERROR, HEADING, COMMAND, PROMPT_USER, PROMPT_PATH)

# Marks at the start of a status line.
MARK_OK = "✓"
MARK_FAIL = "✗"
MARK_WARN = "!"
MARK_SKIP = "–"


@dataclass(frozen=True)
class Span:
    text: str
    style: str = TEXT


Line = list  # list[Span]
Part = Union[str, Span, tuple]  # "text", Span(...), or ("text", style)


def line(*parts: Part) -> Line:
    """A line from strings, spans and (text, style) pairs."""
    spans: Line = []
    for part in parts:
        if isinstance(part, Span):
            spans.append(part)
        elif isinstance(part, tuple):
            spans.append(Span(str(part[0]), part[1]))
        elif part:
            spans.append(Span(str(part)))
    return spans


def plain(spans: Iterable[Span]) -> str:
    return "".join(span.text for span in spans)


def styled(text: str, style: str = TEXT) -> list[Line]:
    """Lines of ``text`` (split at newlines), all in one style."""
    return [[Span(part, style)] if part else [] for part in text.split("\n")]


def truncate(text: str, width: int) -> str:
    """``text`` cut to ``width`` characters, ending in "…" when cut."""
    if width <= 0:
        return ""
    return text if len(text) <= width else text[: width - 1] + "…"


# ----------------------------------------------------------------------------- drawings
_EIGHTHS = " ▏▎▍▌▋▊▉█"   # a cell filled 0/8 .. 8/8 from the left
_LEVELS = " ▁▂▃▄▅▆▇█"    # a cell filled 0/8 .. 8/8 from the bottom
FULL = "█"
EMPTY = "░"


def progress_bar(fraction: float, width: int) -> tuple[str, str]:
    """A bar ``width`` cells wide: (the filled part, the empty part). Eighths of a cell are drawn."""
    width = max(1, width)
    fraction = min(1.0, max(0.0, fraction))
    eighths = round(fraction * width * 8)
    full, part = divmod(eighths, 8)
    filled = FULL * full + (_EIGHTHS[part] if part else "")
    return filled, EMPTY * (width - len(filled))


def sparkline(values: Sequence[float], width: int, top: float | None = None) -> str:
    """The last ``width`` values as a one-line chart; ``top`` (default: the largest value) is a full cell."""
    values = list(values)[-width:] if width > 0 else []
    peak = top if top is not None else max(values, default=0.0)
    if peak <= 0:
        return "▁" * len(values)
    return "".join(_LEVELS[max(1, min(8, round(value / peak * 8)))] for value in values)


def bar_chart(values: Sequence[float], height: int, top: float | None = None) -> list[str]:
    """Vertical bars, one column per value, ``height`` rows high (top row first). Eighths are drawn."""
    peak = top if top is not None else max(values, default=0.0)
    rows = []
    for row in range(height):
        floor = (height - 1 - row) * 8  # eighths below this row
        cells = []
        for value in values:
            level = round(value / peak * height * 8) if peak > 0 else 0
            cells.append(_LEVELS[max(0, min(8, level - floor))])
        rows.append("".join(cells))
    return rows


def table(
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    align: str = "",
    styles: Sequence[str] = (),
    max_width: int = 0,
) -> list[Line]:
    """A table with a header line. ``align`` has one letter per column: l(eft) or r(ight).

    ``styles`` gives each column a style; a cell that is a ``Span`` keeps its own. When
    the table is wider than ``max_width``, the widest column is shortened (with "…")
    until it fits.
    """
    cell_styles = [[value.style if isinstance(value, Span) else None for value in row] for row in rows]
    cells = [[value.text if isinstance(value, Span) else str(value) for value in row] for row in rows]
    widths = [max([len(header)] + [len(row[i]) for row in cells if i < len(row)]) for i, header in enumerate(headers)]
    gap = 2
    if max_width > 0:
        while sum(widths) + gap * (len(widths) - 1) > max_width and max(widths) > 8:
            widths[widths.index(max(widths))] -= 1

    def cell(text: str, i: int) -> str:
        text = truncate(text, widths[i])
        return text.rjust(widths[i]) if i < len(align) and align[i] == "r" else text.ljust(widths[i])

    lines = [[Span((" " * gap).join(cell(h, i) for i, h in enumerate(headers)).rstrip(), HEADING)]]
    for row, own_styles in zip(cells, cell_styles):
        spans = []
        for i in range(len(headers)):
            text = cell(row[i] if i < len(row) else "", i)
            if i == len(headers) - 1:
                text = text.rstrip()
            style = own_styles[i] if i < len(own_styles) and own_styles[i] else None
            spans.append(Span(text, style or (styles[i] if i < len(styles) else TEXT)))
            if i < len(headers) - 1:
                spans.append(Span(" " * gap))
        lines.append(spans)
    return lines


def key_values(pairs: Sequence[tuple[str, object]], value_style: str = TEXT, indent: int = 2) -> list[Line]:
    """Aligned "key   value" lines. A value may be a span, to give it its own style."""
    width = max((len(key) for key, _ in pairs), default=0)
    lines = []
    for key, value in pairs:
        value_span = value if isinstance(value, Span) else Span(str(value), value_style)
        lines.append([Span(" " * indent + key.ljust(width + 2), MUTED), value_span])
    return lines


def columns(words: Sequence[str], width: int, gap: int = 2) -> list[str]:
    """``words`` laid out in as many columns as fit in ``width`` (filled top to bottom, like ls)."""
    if not words:
        return []
    cell = max(len(word) for word in words) + gap
    count = max(1, width // cell)
    rows = -(-len(words) // count)
    lines = []
    for row in range(rows):
        lines.append("".join(words[col * rows + row].ljust(cell) for col in range(count)
                             if col * rows + row < len(words)).rstrip())
    return lines
