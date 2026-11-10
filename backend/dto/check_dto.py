"""The result of one set-up check, e.g. a step of gkonsol's ``gee verify``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

CHECK_OK = "ok"
CHECK_WARN = "warn"   # works, but something deserves attention
CHECK_FAIL = "fail"
CHECK_SKIP = "skip"   # not run, because a check it depends on failed


@dataclass(frozen=True)
class CheckDTO:
    name: str                             # e.g. "Cloud project"
    status: str                           # CHECK_OK | CHECK_WARN | CHECK_FAIL | CHECK_SKIP
    detail: str = ""                      # what was found, e.g. the project id
    hint: str = ""                        # how to fix it, when it did not pass
    duration_ms: Optional[float] = None   # how long the check took, for checks that call a server

    @property
    def passed(self) -> bool:
        return self.status in (CHECK_OK, CHECK_WARN)
