"""Running gkonsol commands: background tasks, pauses, questions and Ctrl+C (no Qt)."""

import pytest

from frontend.gkonsol.effects import Ask, Interrupted, Sleep, Task, task
from frontend.gkonsol.runner import Runner
from tests.gkonsol_fakes import StepScheduler


@pytest.fixture
def setup():
    scheduler, finished, states = StepScheduler(), [], []
    runner = Runner(scheduler, lambda error, interrupted: finished.append((error, interrupted)),
                    lambda: states.append(1))
    return runner, scheduler, finished


def test_a_plain_handler_is_finished_at_once(setup):
    runner, _, finished = setup
    runner.run(None)
    assert finished == [(None, False)] and not runner.running


def test_a_task_resumes_the_command_with_its_result(setup):
    runner, scheduler, finished = setup
    seen = []

    def command():
        seen.append((yield task(lambda a, b: a + b, 2, 3, label="Adding")))

    runner.run(command())
    assert runner.running and runner.waiting_for.label == "Adding" and finished == []
    scheduler.finish_tasks()
    assert seen == [5] and finished == [(None, False)]


def test_a_failed_task_raises_at_the_yield(setup):
    runner, scheduler, finished = setup
    caught = []

    def command():
        try:
            yield Task(lambda: 1 / 0)
        except ZeroDivisionError as exc:
            caught.append(exc)

    runner.run(command())
    scheduler.finish_tasks()
    assert len(caught) == 1 and finished == [(None, False)]


def test_an_unhandled_error_ends_the_command_with_it(setup):
    runner, scheduler, finished = setup

    def command():
        yield Task(lambda: 1 / 0)

    runner.run(command())
    scheduler.finish_tasks()
    assert isinstance(finished[0][0], ZeroDivisionError) and not runner.running


def test_sleep_resumes_after_the_timer(setup):
    runner, scheduler, finished = setup
    ticks = []

    def command():
        for n in range(3):
            ticks.append(n)
            yield Sleep(0.5)

    runner.run(command())
    assert ticks == [0] and scheduler.timers[0][0] == 0.5
    scheduler.fire_timers()
    scheduler.fire_timers()
    assert ticks == [0, 1, 2] and finished == []
    scheduler.fire_timers()
    assert finished == [(None, False)]


def test_a_question_waits_for_the_answer(setup):
    runner, _, finished = setup
    answers = []

    def command():
        answers.append((yield Ask("Sign out? [y/N]", default="n")))

    assert runner.answer("y") is False  # nothing asked yet
    runner.run(command())
    assert runner.asking.prompt == "Sign out? [y/N]"
    assert runner.answer("y") is True
    assert answers == ["y"] and finished == [(None, False)] and runner.asking is None


def test_ctrl_c_interrupts_and_late_results_are_ignored(setup):
    runner, scheduler, finished = setup
    resumed = []

    def command():
        resumed.append((yield Task(lambda: "late")))

    runner.run(command())
    assert runner.interrupt() is True
    assert finished == [(None, True)] and not runner.running
    scheduler.finish_tasks()  # the task ends after Ctrl+C: nobody is waiting for it
    assert resumed == [] and finished == [(None, True)]


def test_a_command_can_handle_ctrl_c_itself(setup):
    runner, scheduler, finished = setup
    said = []

    def command():
        try:
            while True:
                yield Sleep(1)
        except Interrupted:
            said.append("Stopped watching.")

    runner.run(command())
    runner.interrupt()
    assert said == ["Stopped watching."] and finished == [(None, False)]
    scheduler.fire_timers()  # the old timer fires: ignored
    assert finished == [(None, False)]


def test_interrupt_without_a_command_does_nothing(setup):
    runner, _, finished = setup
    assert runner.interrupt() is False and finished == []


def test_stop_closes_the_command_and_runs_its_cleanup(setup):
    runner, scheduler, finished = setup
    cleaned = []

    def command():
        try:
            yield Task(lambda: None)
        finally:
            cleaned.append(True)

    runner.run(command())
    runner.stop()
    assert cleaned == [True] and not runner.running
    scheduler.finish_tasks()
    assert finished == []  # stopped, not finished: nothing more is printed


def test_yielding_something_else_is_an_error(setup):
    runner, _, finished = setup

    def command():
        yield "not an effect"

    runner.run(command())
    assert isinstance(finished[0][0], TypeError)
