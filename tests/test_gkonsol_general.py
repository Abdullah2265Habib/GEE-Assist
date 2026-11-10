"""gkonsol's general commands: help, clear, history, echo, version, exit."""

import pytest

from tests.gkonsol_fakes import terminal


@pytest.fixture
def term():
    return terminal()


def test_help_lists_the_commands_by_group(term):
    printed = term.type("help")
    assert "gkonsol — the GEE-Assist command line" in printed
    assert "not Windows, PowerShell or cmd commands" in printed
    assert "General" in printed and "  history" in printed and "Ctrl+C stops a command" in printed


def test_help_for_one_command(term):
    printed = term.type("help history")
    assert "history — Show the commands typed before" in printed
    assert "Usage\n  history [COUNT] [options]" in printed
    assert "--clear" in printed and "Examples" in printed and "!gee" in printed


def test_help_for_an_unknown_command(term):
    printed = term.type("help histroy")
    assert "No help for 'histroy'" in printed and "Did you mean 'history'?" in printed


def test_question_mark_is_help(term):
    assert "gkonsol — the GEE-Assist command line" in term.type("?")


def test_help_completes_command_names(term):
    assert "history" in term.shell.complete("help hi")[1]


def test_clear_empties_the_terminal(term):
    term.type("echo hi")
    term.type("clear")
    assert term.output() == ""


def test_history_lists_numbered_commands(term):
    term.type("echo one")
    term.type("echo two")
    printed = term.type("history")
    assert "1  echo one\n2  echo two\n3  history" in printed and "!3" in printed
    assert term.type("history 1").split("\n")[1] == "4  history 1"


def test_history_clear(term):
    term.type("echo one")
    assert "cleared" in term.type("history --clear")
    assert term.shell.history.entries == []


def test_history_needs_a_number(term):
    assert "'many' is not a number" in term.type("history many")


def test_echo_prints_the_line_as_typed(term):
    assert term.type('echo  "quoted" and it\'s fine').endswith('"quoted" and it\'s fine')


def test_version_lists_the_libraries(term):
    printed = term.type("version")
    assert "gkonsol" in printed and "Python" in printed and "PyQt / Qt" in printed and "Earth Engine API" in printed


def test_exit_hides_the_terminal(term):
    term.type("exit")
    assert term.panel.closed
