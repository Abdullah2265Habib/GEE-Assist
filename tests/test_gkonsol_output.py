"""What gkonsol commands print: messages, tables and live (redrawn) lines."""

from frontend.gkonsol import text
from frontend.gkonsol.output import BufferSink, Writer
from frontend.gkonsol.text import Span


def _writer(columns=60):
    sink = BufferSink(columns)
    return Writer(sink), sink


def test_messages_carry_a_mark_and_a_style():
    out, sink = _writer()
    out.success("Signed in")
    out.warning("No saved sign-in")
    out.error("Earth Engine refused the request")
    out.hint("run gee login")
    assert sink.text() == ("✓ Signed in\n! No saved sign-in\n✗ Earth Engine refused the request\n"
                           "  → run gee login")
    assert sink.lines[0][1].style == text.SUCCESS and sink.lines[2][0].style == text.ERROR


def test_text_is_split_into_lines_and_blank_lines_are_kept():
    out, sink = _writer()
    out.text("one\ntwo")
    out.blank()
    out.muted("three")
    assert sink.text() == "one\ntwo\n\nthree" and sink.lines[3] == [Span("three", text.MUTED)]


def test_tables_fit_the_terminal_width():
    out, sink = _writer(columns=24)
    out.table(["ID", "NAME"], [["1", "Sentinel-2_73.8231_33.2334"]])
    assert all(len(text.plain(line)) <= 24 for line in sink.lines)


def test_pairs_are_aligned():
    out, sink = _writer()
    out.pairs([("Username", "ayesha"), ("Role", "User")])
    assert sink.text() == "  Username  ayesha\n  Role      User"


def test_live_lines_are_redrawn_in_place_and_other_output_goes_above():
    out, sink = _writer()
    out.print("Starting")
    live = out.live()
    live.update([text.line("10%")])
    live.update([text.line("55%")])
    out.print("Chunk 1 merged")
    assert sink.text() == "Starting\nChunk 1 merged\n55%"
    live.done()
    live.update([text.line("ignored after done")])
    assert sink.text() == "Starting\nChunk 1 merged\n55%" and sink.live == []


def test_live_lines_can_be_removed_when_done():
    out, sink = _writer()
    with out.live() as live:
        live.update([text.line("spinner")])
        live.done(keep=False)
    assert sink.text() == ""


def test_clear_keeps_a_live_region():
    out, sink = _writer()
    out.print("old")
    out.live().update([text.line("42%")])
    out.clear()
    assert sink.text() == "42%"


def test_columns_never_get_too_small():
    out, _ = _writer(columns=5)
    assert out.columns == 20
