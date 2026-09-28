"""Gemini provider HTTP handling, with a mock transport (no network, no key)."""

import dataclasses
import json

import httpx
import pytest

from app.extraction import gemini
from app.extraction.base import ExtractionError


@pytest.fixture(autouse=True)
def reset_cooldown():
    gemini._cooldown_until[0] = 0.0
    yield
    gemini._cooldown_until[0] = 0.0


def patch_client(monkeypatch, handler):
    real = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(gemini.httpx, "Client", factory)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


def ok_response(text):
    return {"candidates": [{"content": {"parts": [{"text": "thinking…", "thought": True}, {"text": text}]}}]}


def test_success_and_request_shape(monkeypatch):
    seen = {}

    def handler(request):
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok_response('{"candidates": [{"quote": "اقرأ باسم ربك", "reference_text": ""}]}'))

    patch_client(monkeypatch, handler)
    out = gemini.GeminiProvider().extract("مقال")
    assert [s.quote for s in out] == ["اقرأ باسم ربك"] and out[0].reference_text is None
    assert seen["key"] == "test-key" and "key=" not in seen["url"]  # key sent in a header, not the URL
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert "<article>" in seen["body"]["contents"][0]["parts"][0]["text"]


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(429, json={}),
        lambda r: httpx.Response(500, text="oops"),
        lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}),
        lambda r: httpx.Response(200, json=ok_response("not json at all")),
    ],
)
def test_failures_raise_extraction_error(monkeypatch, handler):
    patch_client(monkeypatch, handler)
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    with pytest.raises(ExtractionError):
        gemini.GeminiProvider().extract("مقال")


def test_retry_on_overload_then_fallback(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.path.rsplit("/", 1)[-1])
        if "backup-model" in request.url.path:
            return httpx.Response(200, json=ok_response('{"candidates": []}'))
        return httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}})

    patch_client(monkeypatch, handler)
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    monkeypatch.setattr(gemini, "settings", dataclasses.replace(gemini.settings, gemini_fallback_models=("backup-model",)))
    p = gemini.GeminiProvider()
    assert p.extract("مقال") == []
    assert len(calls) == 3 and p.used_model == "backup-model"


def test_quota_is_not_retried(monkeypatch):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, json={})

    patch_client(monkeypatch, handler)
    with pytest.raises(ExtractionError, match="الحصة"):
        gemini.GeminiProvider().extract("مقال")
    assert len(calls) == 1


def test_timeout(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    patch_client(monkeypatch, handler)
    with pytest.raises(ExtractionError, match="مهلة"):
        gemini.GeminiProvider().extract("مقال")


def test_no_key_means_unavailable(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert gemini.GeminiProvider().available() is False


def test_cooldown_skips_calls_after_failure(monkeypatch):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, json={})

    patch_client(monkeypatch, handler)
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    with pytest.raises(ExtractionError, match="503"):
        gemini.GeminiProvider().extract("مقال")
    n = len(calls)
    with pytest.raises(ExtractionError, match="مؤقتًا"):
        gemini.GeminiProvider().extract("مقال")
    assert len(calls) == n  # no network call during the cooldown


def test_timeout_moves_to_fallback_without_retrying_same_model(monkeypatch):
    calls = []

    def handler(request):
        model = request.url.path.rsplit("/", 1)[-1].split(":")[0]
        calls.append(model)
        if model == "backup-model":
            return httpx.Response(200, json=ok_response('{"candidates": [{"quote": "اقرأ"}]}'))
        raise httpx.ReadTimeout("slow", request=request)

    patch_client(monkeypatch, handler)
    monkeypatch.setattr(gemini, "settings", dataclasses.replace(gemini.settings, gemini_fallback_models=("backup-model",)))
    p = gemini.GeminiProvider()
    assert [s.quote for s in p.extract("مقال")] == ["اقرأ"]
    assert calls == [gemini.settings.gemini_model, "backup-model"]
    assert gemini._cooldown_remaining() == 0  # success clears the cooldown


def test_default_budget_is_demo_friendly():
    from app.config import Settings

    st = Settings()
    assert st.ai_timeout <= 12 and st.ai_attempt_timeout <= st.ai_timeout
