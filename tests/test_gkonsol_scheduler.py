"""gkonsol's Qt scheduler: background tasks and timers that die with their owner."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtCore import QObject, QThreadPool  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from frontend.gkonsol.scheduler import QtScheduler  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _wait_for(condition, ms=3000):
    for _ in range(ms // 10):
        if condition():
            return True
        QTest.qWait(10)
    return condition()


def test_tasks_run_in_the_background_and_call_back(app):
    owner, results = QObject(), []
    QtScheduler(owner).run_task(lambda a, b: a * b, (6, 7), results.append, results.append)
    assert _wait_for(lambda: results == [42])


def test_task_errors_are_delivered(app):
    owner, errors = QObject(), []
    QtScheduler(owner).run_task(lambda: 1 / 0, (), lambda _: None, errors.append)
    assert _wait_for(lambda: len(errors) == 1) and isinstance(errors[0], ZeroDivisionError)


def test_timers_fire_once(app):
    owner, fired = QObject(), []
    QtScheduler(owner).call_later(0.01, lambda: fired.append(1))
    assert _wait_for(lambda: fired == [1])
    QTest.qWait(50)
    assert fired == [1]


def test_timers_of_a_deleted_owner_never_fire(app):
    owner, fired = QObject(), []
    QtScheduler(owner).call_later(0.05, lambda: fired.append(1))
    owner.deleteLater()
    QTest.qWait(150)
    QThreadPool.globalInstance().waitForDone(1000)
    assert fired == []
