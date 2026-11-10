"""gkonsol's shell: running typed lines, errors, history, questions, Ctrl+C and Tab completion."""

import pytest

from backend.exceptions import GEEError
from frontend.gkonsol.command import Command, Registry
from frontend.gkonsol.effects import Ask, Sleep, Task
from frontend.gkonsol.parser import Option, UsageError
from tests.gkonsol_fakes import terminal


def _registry(log: list) -> Registry:
    registry = Registry()
    registry.add(Command("echo", "Print text", lambda ctx, args: ctx.out.print(args.raw), raw=True, group="General"))

    def greet(ctx, args):
        ctx.out.print(f"hello {args.word(0, 'you')}{'!' if args.flag('loud') else ''}")

    registry.add(Command("greet", "Greet", greet, params="[NAME]", max_args=1,
                         options=[Option("loud", short="l")], group="General",
                         completer=lambda ctx, typed, prefix: ["ayesha", "abdullah", "bilal"]))

    def confirm(ctx, args):
        answer = yield Ask("Really? [y/N]", default="n", choices=("y", "n"))
        log.append(answer)

    def secret(ctx, args):
        log.append((yield Ask("Password:", secret=True)))

    def slow(ctx, args):
        log.append((yield Task(lambda: 42, label="Thinking")))

    def watch(ctx, args):
        while True:
            yield Sleep(0.5)

    registry.add(Command("confirm", "Ask first", confirm, group="General"))
    registry.add(Command("secret", "Ask a secret", secret, group="General"))
    registry.add(Command("slow", "Background task", slow, group="General"))
    registry.add(Command("watch", "Runs until Ctrl+C", watch, group="General"))
    registry.add(Command("fail", "Fails", lambda ctx, args: (_ for _ in ()).throw(GEEError("Earth Engine refused")),
                         group="General"))
    registry.add(Command("crash", "Crashes", lambda ctx, args: 1 / 0, group="General"))
    registry.add(Command("bad", "Usage error", lambda ctx, args: (_ for _ in ()).throw(UsageError("Give a number.")),
                         group="General"))

    download = registry.add(Command("download", "Downloads", aliases=("dl",), group="Downloads"))
    download.add(Command("start", "Start", lambda ctx, args: ctx.out.print(f"started {args.words}"),
                         params="[REQUEST]", max_args=1, options=[Option("detach", short="d")]))
    download.add(Command("list", "List", lambda ctx, args: ctx.out.print("no downloads"), aliases=("ls",)))
    users = registry.add(Command("users", "Manage users", admin=True, group="Account"))
    users.add(Command("list", "List users", lambda ctx, args: ctx.out.print("2 users")))
    return registry


@pytest.fixture
def log():
    return []


@pytest.fixture
def term(log):
    return terminal(_registry(log))


# ------------------------------------------------------------------ running lines
def test_the_typed_line_is_shown_after_the_prompt(term):
    assert term.type("greet bilal") == "ayesha@gkonsol ~ $ greet bilal\nhello bilal"


def test_the_prompt_shows_the_page(term):
    term.app.page = "downloads"
    assert term.type("greet").startswith("ayesha@gkonsol ~/downloads $ greet")


def test_blank_lines_do_nothing(term):
    term.type("   ")
    assert term.shell.history.entries == []


def test_options_and_arguments_reach_the_command(term):
    assert term.type("greet -l ayesha").endswith("hello ayesha!")
    assert term.type("dl start 2 --detach").endswith("started ['2']")


def test_raw_commands_get_the_line_as_typed(term):
    assert term.type("echo it's   \"fine\"").endswith("it's   \"fine\"")
    assert term.type("echo 'quoted whole'").endswith("quoted whole")


def test_unknown_commands_get_suggestions(term):
    printed = term.type("downlod")
    assert "✗ 'downlod' is not a gkonsol command." in printed
    assert "Did you mean 'download'?" in printed and "Type 'help'" in printed


def test_windows_commands_are_explained(term):
    printed = term.type("dir")
    assert "Windows and PowerShell commands do not work here" in printed
    assert "gee login" in term.type("earthengine authenticate")


def test_a_group_without_subcommand_shows_its_help(term):
    printed = term.type("download")
    assert "Subcommands" in printed and "start" in printed and "list" in printed


def test_unknown_subcommands_are_reported(term):
    printed = term.type("download stop")
    assert "'download' has no subcommand 'stop'" in printed and "help download" in printed


def test_admin_commands_are_refused_for_other_users(term):
    assert "'users list' is for administrators only." in term.type("users list")
    admin = terminal(_registry([]), role="admin")
    assert admin.type("users list").endswith("2 users")


@pytest.mark.parametrize("line, message", [
    ("greet a b", "Too many arguments for 'greet': b"),
    ("greet --shout", "Unknown option --shout"),
    ("bad", "Give a number."),
    ('greet "open', "The quote \" is not closed"),
])
def test_usage_errors_show_how_to_use_the_command(term, line, message):
    printed = term.type(line)
    assert message in printed and "Usage:" in printed


def test_backend_errors_are_shown_as_they_are(term):
    assert term.type("fail").endswith("✗ Earth Engine refused")


def test_unexpected_errors_are_reported_not_raised(term):
    assert "Something went wrong: ZeroDivisionError" in term.type("crash")


# ------------------------------------------------------------------ history
def test_commands_are_kept_in_the_history_and_can_be_repeated(term):
    term.type("greet bilal")
    printed = term.type("!!")
    assert printed.split("\n")[1:] == ["greet bilal", "hello bilal"]  # the expanded command, then its output
    assert term.shell.history.entries == ["greet bilal"]
    assert "no such command" in term.type("!nothing")


# ------------------------------------------------------------------ long commands
def test_questions_are_answered_by_the_next_line(term, log):
    term.type("confirm")
    assert term.shell.runner.asking.prompt == "Really? [y/N]"
    assert term.type("y").endswith("Really? [y/N] y")
    assert log == ["y"] and term.shell.runner.asking is None


def test_an_empty_answer_takes_the_default(term, log):
    term.type("confirm")
    term.type("")
    assert log == ["n"]


def test_secret_answers_are_hidden(term, log):
    term.type("secret")
    assert term.type("hunter2").endswith("Password: •••••••")
    assert log == ["hunter2"]


def test_background_tasks_show_a_status_and_deliver_the_result(term, log):
    term.type("slow", settle=False)
    assert term.shell.status() == "Thinking…  (Ctrl+C to stop)"
    term.scheduler.finish_tasks()
    assert log == [42] and term.shell.status() == ""


def test_typing_while_a_command_runs_is_refused(term):
    term.type("watch")
    assert "A command is still running. Press Ctrl+C to stop it." in term.type("greet")
    assert term.shell.status() == "watch is running  (Ctrl+C to stop)"


def test_ctrl_c_stops_the_running_command(term):
    term.type("watch")
    term.shell.interrupt()
    assert term.output().endswith("^C") and term.shell.running is None
    term.shell.interrupt()  # nothing running: nothing happens
    assert term.output().endswith("^C")


def test_stop_ends_the_command_quietly(term):
    term.type("watch")
    term.shell.stop()
    assert term.shell.running is None and not term.output().endswith("^C")


# ------------------------------------------------------------------ completion
@pytest.mark.parametrize("typed, expected", [
    ("", ["echo", "greet", "confirm", "secret", "slow", "watch", "fail", "crash", "bad", "download"]),
    ("gr", ["greet"]),
    ("d", ["download"]),
    ("dl", ["dl"]),                       # an alias, when no name matches
    ("download ", ["start", "list"]),
    ("download s", ["start"]),
    ("dl start --", ["--detach"]),
    ("greet a", ["ayesha", "abdullah"]),
    ("greet x", []),
    ("users ", []),                       # admin only
    ("nothing ", []),
])
def test_tab_completes_commands_subcommands_options_and_values(term, typed, expected):
    start, candidates = term.shell.complete(typed)
    assert candidates == expected and start == len(typed) - len(typed.split(" ")[-1])


def test_tab_offers_the_answers_to_a_question(term):
    term.type("confirm")
    assert term.shell.complete("") == (0, ["y", "n"])


def test_admins_can_complete_admin_commands():
    admin = terminal(_registry([]), role="admin")
    assert "users" in admin.shell.complete("")[1]
    assert admin.shell.complete("users ")[1] == ["list"]
