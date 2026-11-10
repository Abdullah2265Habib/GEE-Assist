"""Runs gkonsol's background tasks on the app's worker threads and its timers with QTimer.

Both belong to an owner widget (the terminal panel): when it is deleted (signing out),
results and timers that come later are dropped instead of reaching deleted widgets.
"""

from __future__ import annotations

from typing import Any, Callable

from PyQt6.QtCore import QObject, QTimer

from frontend.workers.task_worker import run_task


class QtScheduler:
    def __init__(self, owner: QObject):
        self._owner = owner

    def run_task(self, fn: Callable[..., Any], args: tuple, on_success: Callable[[Any], None],
                 on_error: Callable[[BaseException], None]) -> None:
        run_task(self._owner, fn, *args, on_success=on_success, on_error=on_error)

    def call_later(self, seconds: float, callback: Callable[[], None]) -> None:
        timer = QTimer(self._owner)  # deleted with the owner, so it cannot fire afterwards
        timer.setSingleShot(True)
        timer.timeout.connect(callback)
        timer.timeout.connect(timer.deleteLater)
        timer.start(max(0, int(seconds * 1000)))
