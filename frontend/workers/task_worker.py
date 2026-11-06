"""Run blocking backend calls (network requests) off the UI thread.

    run_task(self, self._facade.log_in, username, password,
             on_success=self._on_logged_in, on_error=self._on_failed)

Callbacks run on the UI thread. They are dropped if ``owner`` has been deleted meanwhile.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

logger = logging.getLogger(__name__)


class _TaskSignals(QObject):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(object)


class _Task(QRunnable):
    def __init__(self, fn: Callable[..., Any], args: tuple, signals: _TaskSignals):
        super().__init__()
        self._fn = fn
        self._args = args
        self._signals = signals

    def run(self) -> None:
        try:
            result = self._fn(*self._args)
        except Exception as exc:  # delivered to on_error
            if not _is_expected(exc):
                logger.exception("Background task failed")
            self._emit(self._signals.failed, exc)
        else:
            self._emit(self._signals.succeeded, result)

    @staticmethod
    def _emit(signal, value: Any) -> None:
        try:
            signal.emit(value)
        except RuntimeError:
            pass  # the owner widget (and with it the signals object) was deleted


def _is_expected(exc: Exception) -> bool:
    from backend.exceptions import GeeAssistError

    return isinstance(exc, GeeAssistError)


def run_task(
    owner: QObject,
    fn: Callable[..., Any],
    *args: Any,
    on_success: Callable[[Any], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
) -> None:
    # Parented to the owner (UI thread), so the callbacks are queued back onto the UI thread.
    signals = _TaskSignals(owner)
    if on_success:
        signals.succeeded.connect(on_success)
    if on_error:
        signals.failed.connect(on_error)
    signals.succeeded.connect(signals.deleteLater)
    signals.failed.connect(signals.deleteLater)
    QThreadPool.globalInstance().start(_Task(fn, args, signals))
