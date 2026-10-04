"""Per-provider record of the most recent *real* call, and a failure cooldown.

"Configured" (a key is set) is not the same as "working". Health and the UI
report what actually happened on the last call made by this server instance.
State is per process (per serverless instance) and never contains article text.
"""

from __future__ import annotations

import threading
import time


class CallTracker:
    def __init__(self) -> None:
        # Counts of real calls since this process started (for an external monitor's 429-rate alert). Counts only, no text.
        self._lock = threading.Lock()
        self.counts = {"calls": 0, "ok": 0, "failed": 0, "rate_limited": 0}
        self.counts_since = time.time()
        self.cooldown_until = [0.0]  # monotonic time until which calls are skipped
        # outcome: never_called | ok | failed
        self.last: dict = {"outcome": "never_called", "at": None, "model": None, "detail": None,
                           "http_status": None, "elapsed_ms": None}

    def record(self, outcome: str, model: str | None, detail: str | None = None,
               http_status: int | None = None, elapsed_ms: int | None = None) -> None:
        self.last.update(outcome=outcome, at=time.time(), model=model, detail=detail,
                         http_status=http_status, elapsed_ms=elapsed_ms)
        with self._lock:
            self.counts["calls"] += 1
            if outcome == "ok":
                self.counts["ok"] += 1
            else:
                self.counts["failed"] += 1
            if http_status == 429:
                self.counts["rate_limited"] += 1

    def cooldown_remaining(self) -> int:
        return max(0, int(self.cooldown_until[0] - time.monotonic() + 0.999))

    def start_cooldown(self, seconds: float) -> None:
        if seconds > 0:
            self.cooldown_until[0] = time.monotonic() + seconds

    def clear_cooldown(self) -> None:
        self.cooldown_until[0] = 0.0

    def recent(self) -> dict:
        """Counters since process start: calls made, answered, failed, and failed with HTTP 429 (a subset of failed)."""
        with self._lock:
            return {**self.counts, "since": self.counts_since}

    def status(self) -> dict:
        return {**self.last, "cooldown_seconds": self.cooldown_remaining()}
