"""gkonsol's styled text and character drawings (no Qt)."""

from frontend.gkonsol import text
from frontend.gkonsol.text import Span


def test_a_line_takes_strings_spans_and_pairs():
    spans = text.line("gee ", Span("verify", text.ACCENT), (" ok", text.SUCCESS), "")
    assert spans == [Span("gee "), Span("verify", text.ACCENT), Span(" ok", text.SUCCESS)]
    assert text.plain(spans) == "gee verify ok"


def test_styled_text_is_split_into_lines():
    assert text.styled("a\n\nb", text.MUTED) == [[Span("a", text.MUTED)], [], [Span("b", text.MUTED)]]


def test_truncate_marks_the_cut():
    assert text.truncate("Sentinel-2", 20) == "Sentinel-2"
    assert text.truncate("Sentinel-2", 6) == "Senti…"
    assert text.truncate("abc", 0) == ""


def test_progress_bar_draws_eighths_of_a_cell():
    assert text.progress_bar(0.0, 4) == ("", "░░░░")
    assert text.progress_bar(1.0, 4) == ("████", "")
    assert text.progress_bar(0.5, 4) == ("██", "░░")
    filled, empty = text.progress_bar(0.53, 10)  # 5.3 cells: 5 full and 2/8 of the next
    assert filled == "█████▎" and empty == "░░░░"
    assert len(filled + empty) == 10


def test_progress_bar_clamps_the_fraction():
    assert text.progress_bar(1.7, 3) == ("███", "") and text.progress_bar(-1, 3) == ("", "░░░")


def test_sparkline_scales_to_the_largest_value():
    assert text.sparkline([0, 4, 8], 10) == "▁▄█"
    assert text.sparkline([1, 2, 3, 4], 2) == "▆█"          # only the last values fit
    assert text.sparkline([0, 0], 5) == "▁▁"                 # nothing yet: a flat line
    assert text.sparkline([2, 4], 5, top=8) == "▂▄"


def test_bar_chart_stacks_cells_from_the_bottom():
    rows = text.bar_chart([0, 4, 8, 16], height=2)  # 2 rows = 16 eighths; 16 is the top
    assert rows == ["   █", " ▄██"]
    assert text.bar_chart([0, 0], height=2) == ["  ", "  "]


def test_table_aligns_columns_and_styles_them():
    lines = text.table(["#", "NAME"], [[1, "Sentinel-2"], [12, "Landsat 8"]], align="rl",
                       styles=(text.MUTED, text.ACCENT))
    assert [text.plain(line) for line in lines] == [" #  NAME", " 1  Sentinel-2", "12  Landsat 8"]
    assert lines[0][0].style == text.HEADING and lines[1][2] == Span("Sentinel-2", text.ACCENT)


def test_table_shortens_the_widest_column_to_fit():
    lines = text.table(["ID", "FOLDER"], [["a1", "x" * 40]], max_width=20)
    assert all(len(text.plain(line)) <= 20 for line in lines)
    assert text.plain(lines[1]).endswith("…")


def test_key_values_are_aligned():
    lines = text.key_values([("User", "ayesha"), ("Role", Span("Administrator", text.ACCENT))])
    assert [text.plain(line) for line in lines] == ["  User  ayesha", "  Role  Administrator"]
    assert lines[1][1].style == text.ACCENT


def test_columns_fill_top_to_bottom():
    assert text.columns(["aa", "bb", "cc", "dd", "ee"], width=12) == ["aa  cc  ee", "bb  dd"]
    assert text.columns([], 10) == []
