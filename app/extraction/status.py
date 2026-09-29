"""Per-provider record of the most recent *real* call, and a failure cooldown.

"Configured" (a key is set) is not the same as "working". Health and the UI
report what actually happened on the last call made by this server instance.
State is per process (per serverless instance) and never contains article text.
"""

from __future__ import annotations

import time


class CallTracker:
    def __init__(self) -> None:
        self.cooldown_until = [0.0]  # monotonic time until which calls are skipped
        # outcome: never_called | ok | failed
        self.last: dict = {"outcome": "never_called", "at": None, "model": None, "detail": None,
                           "http_status": None, "elapsed_ms": None}

    def record(self, outcome: str, model: str | None, detail: str | None = None,
               http_status: int | None = None, elapsed_ms: int | None = None) -> None:
        self.last.update(outcome=outcome, at=time.time(), model=model, detail=detail,
                         http_status=http_status, elapsed_ms=elapsed_ms)

    def cooldown_remaining(self) -> int:
        return max(0, int(self.cooldown_until[0] - time.monotonic() + 0.999))

    def start_cooldown(self, seconds: float) -> None:
        if seconds > 0:
            self.cooldown_until[0] = time.monotonic() + seconds

    def clear_cooldown(self) -> None:
        self.cooldown_until[0] = 0.0

    def status(self) -> dict:
        return {**self.last, "cooldown_seconds": self.cooldown_remaining()}
