"""Fields of /api/health meant for an external uptime monitor: source_ok, ?deep=1 and the ai_recent counters (counts only)."""

import json

from fastapi.testclient import TestClient

import app.main as main
from app.extraction.status import CallTracker


class RecordingSource:
    def __init__(self, loaded=False, stale=False, fail=False):
        self.loaded, self.stale, self.fail, self.calls = loaded, stale, fail, 0

    def get(self):
        from app.quran_source import SourceUnavailable

        self.calls += 1
        if self.fail:
            raise SourceUnavailable("offline")
        self.loaded = True
        return object()

    def status(self):
        return {"loaded": self.loaded, "stale": self.stale, "last_error": "ConnectError" if self.fail else None}


class FakeProvider:
    name, label = "fake", "Fake"

    def __init__(self):
        self.tracker = CallTracker()


def test_tracker_counts_calls_failures_and_429():
    t = CallTracker()
    assert t.recent() | {"since": 0} == {"calls": 0, "ok": 0, "failed": 0, "rate_limited": 0, "since": 0}
    t.record("ok", "m", None, 200, 900)
    t.record("failed", "m", "429", 429, 50)
    t.record("failed", "m", "timeout", None, 8000)
    t.record("failed", "m", "503", 503, 20)
    r = t.recent()
    assert (r["calls"], r["ok"], r["failed"], r["rate_limited"]) == (4, 1, 3, 1)
    assert t.status()["outcome"] == "failed"  # the last-call record is unchanged in shape


def test_health_without_model_and_without_deep_fetches_nothing(monkeypatch):
    src = RecordingSource(loaded=False)
    monkeypatch.setattr(main, "source", src)
    monkeypatch.setattr(main, "get_provider", lambda: None)
    h = TestClient(main.app).get("/api/health").json()
    assert src.calls == 0  # Render's own health check never triggers a Quranpedia request
    assert h["source_ok"] is False and h["ai_recent"] is None and h["status"] == "ok"


def test_health_deep_loads_the_source(monkeypatch):
    src = RecordingSource(loaded=False)
    monkeypatch.setattr(main, "source", src)
    monkeypatch.setattr(main, "get_provider", lambda: None)
    h = TestClient(main.app).get("/api/health?deep=1").json()
    assert src.calls == 1 and h["source_ok"] is True


def test_health_source_not_ok_when_stale_or_unreachable(monkeypatch):
    monkeypatch.setattr(main, "get_provider", lambda: None)
    monkeypatch.setattr(main, "source", RecordingSource(loaded=True, stale=True))
    assert TestClient(main.app).get("/api/health?deep=1").json()["source_ok"] is False
    monkeypatch.setattr(main, "source", RecordingSource(fail=True))
    res = TestClient(main.app).get("/api/health?deep=1")
    assert res.status_code == 200  # the monitor reads source_ok; the endpoint itself stays up
    assert res.json()["source_ok"] is False and res.json()["source"]["last_error"] == "ConnectError"


def test_health_ai_recent_has_counts_only(monkeypatch):
    p = FakeProvider()
    p.tracker.record("failed", "m", "429", 429, 40)
    p.tracker.record("ok", "m", None, 200, 800)
    monkeypatch.setattr(main, "get_provider", lambda: p)
    monkeypatch.setattr(main, "source", RecordingSource(loaded=True))
    h = TestClient(main.app).get("/api/health").json()
    assert set(h["ai_recent"]) == {"calls", "ok", "failed", "rate_limited", "since"}
    assert (h["ai_recent"]["calls"], h["ai_recent"]["rate_limited"]) == (2, 1)
    assert all(isinstance(v, (int, float)) for v in h["ai_recent"].values())
    assert not any("؀" <= ch <= "ۿ" for ch in json.dumps(h["ai_recent"], ensure_ascii=False))


def test_groq_calls_feed_the_counters_and_cooldown_skips_do_not(monkeypatch):
    """Mock transport only (no network, fake key), as in tests/test_groq.py."""
    import httpx
    import pytest

    from app.extraction import groq
    from app.extraction.base import ExtractionError

    real = httpx.Client
    replies = [httpx.Response(429, json={"error": {"message": "rate", "type": "tokens"}}),
               httpx.Response(200, json={"model": "m", "choices": [{"message": {"content": '{"candidates": []}'},
                                                                     "finish_reason": "stop"}]})]
    sent = []

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(lambda request: (sent.append(1), replies[len(sent) - 1])[1])
        return real(*args, **kwargs)

    monkeypatch.setattr(groq.httpx, "Client", factory)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    before = groq._tracker.recent()
    try:
        with pytest.raises(ExtractionError):
            groq.GroqProvider().extract("مقال")
        with pytest.raises(ExtractionError):  # inside the cooldown: no call is made, nothing is counted
            groq.GroqProvider().extract("مقال")
        groq._tracker.clear_cooldown()
        groq.GroqProvider().extract("مقال")
    finally:
        groq._tracker.clear_cooldown()
    after = groq._tracker.recent()
    assert len(sent) == 2
    delta = {k: after[k] - before[k] for k in ("calls", "ok", "failed", "rate_limited")}
    assert delta == {"calls": 2, "ok": 1, "failed": 1, "rate_limited": 1}


def test_documented_monitor_keywords_match_the_raw_answer(monkeypatch):
    """docs/RENDER_DEPLOY.md tells a keyword monitor to look for these exact strings in the compact JSON."""
    p = FakeProvider()
    p.tracker.record("failed", "m", "429", 429, 40)
    monkeypatch.setattr(main, "get_provider", lambda: p)
    monkeypatch.setattr(main, "source", RecordingSource(loaded=True))
    raw = TestClient(main.app).get("/api/health?deep=1").text
    assert '"source_ok":true' in raw and '"http_status":429' in raw
    monkeypatch.setattr(main, "source", RecordingSource(fail=True))
    assert '"source_ok":true' not in TestClient(main.app).get("/api/health?deep=1").text


def test_health_reports_the_output_token_reservation_only_for_groq(monkeypatch):
    """The reservation is a configuration number (no secret); it helps read a live OTPM 429 without the host's dashboard."""
    from fastapi.testclient import TestClient

    import app.main as main

    class FakeGroq:
        name, label, tracker = "groq", "Groq (test)", None

    monkeypatch.setattr(main, "get_provider", lambda: FakeGroq())
    body = TestClient(main.app).get("/api/health").json()
    assert body["ai_max_completion_tokens"] == main.settings.groq_max_completion_tokens
    monkeypatch.setattr(main, "get_provider", lambda: None)
    assert TestClient(main.app).get("/api/health").json()["ai_max_completion_tokens"] is None
