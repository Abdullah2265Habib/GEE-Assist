"""Splitting gkonsol command lines into words, options and arguments."""

import pytest

from frontend.gkonsol.parser import Option, UsageError, parse, tokenize

OPTIONS = [
    Option("detach", "Do not follow the download", short="d"),
    Option("yes", "Do not ask", short="y"),
    Option("page", "Page number", short="p", value="N"),
    Option("format", "Output format", value="FORMAT", choices=("table", "json")),
]


# ------------------------------------------------------------------ words
def test_words_are_split_at_spaces():
    assert tokenize("  download   start 2 ") == ["download", "start", "2"]


def test_quotes_keep_spaces_in_one_word():
    assert tokenize('form set output "D:\\GEE data"') == ["form", "set", "output", "D:\\GEE data"]
    assert tokenize("ask 'NDVI of Lahore'") == ["ask", "NDVI of Lahore"]
    assert tokenize('a"b c"d') == ["ab cd"]


def test_backslashes_are_ordinary_characters():
    assert tokenize(r"form aoi file C:\Users\me\aoi.geojson") == ["form", "aoi", "file", r"C:\Users\me\aoi.geojson"]


def test_empty_quotes_are_a_word():
    assert tokenize('echo "" x') == ["echo", "", "x"]


def test_an_unclosed_quote_is_an_error():
    with pytest.raises(UsageError, match='quote "'):
        tokenize('form set output "D:\\GEE')


# ------------------------------------------------------------------ options
def test_flags_and_arguments():
    args = parse(["3", "--detach", "-y"], OPTIONS)
    assert args.words == ["3"] and args.flag("detach") and args.flag("yes")
    assert not args.flag("page")


def test_options_with_values():
    assert parse(["--page", "2"], OPTIONS).value("page") == "2"
    assert parse(["--page=3"], OPTIONS).value("page") == "3"
    assert parse(["-p", "4"], OPTIONS).value("page") == "4"
    assert parse(["-p5"], OPTIONS).value("page") == "5"


def test_combined_flags():
    args = parse(["-dy"], OPTIONS)
    assert args.flag("detach") and args.flag("yes")
    assert parse(["-dp", "7"], OPTIONS).value("page") == "7"


def test_negative_numbers_are_arguments():
    args = parse(["-73.5", "40.6", "-73.4", "-.5", "-1."], OPTIONS)
    assert args.words == ["-73.5", "40.6", "-73.4", "-.5", "-1."]


def test_double_dash_ends_the_options():
    assert parse(["--", "--detach", "-y"], OPTIONS).words == ["--detach", "-y"]


def test_a_lone_dash_is_an_argument():
    assert parse(["-"], OPTIONS).words == ["-"]


@pytest.mark.parametrize("words, message", [
    (["--nope"], "Unknown option --nope"),
    (["-x"], "Unknown option -x"),
    (["--page"], r"--page needs a value \(N\)"),
    (["-p"], r"-p needs a value \(N\)"),
    (["--detach=yes"], "does not take a value"),
    (["--format", "xml"], "must be one of: table, json"),
])
def test_mistakes_are_explained(words, message):
    with pytest.raises(UsageError, match=message):
        parse(words, OPTIONS)


def test_values_with_defaults():
    args = parse([], OPTIONS)
    assert args.value("page", "1") == "1" and args.word(0) is None and args.word(0, "x") == "x"


def test_option_syntax_for_help():
    assert OPTIONS[0].syntax() == "-d, --detach"
    assert OPTIONS[3].syntax() == "    --format FORMAT"
