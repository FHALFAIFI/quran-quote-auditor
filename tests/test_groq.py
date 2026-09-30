"""Groq provider HTTP handling with a mock transport (no network, no real key).

These tests prove request shape and failure handling only. They do NOT show
that the real model extracts quotations well; see docs/TEST_LOG.md for real calls.
"""

import dataclasses
import json

import httpx
import pytest

import app.audit as audit
from app.extraction import base, groq
from app.extraction.base import ExtractionError


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    groq._tracker.clear_cooldown()
    groq._tracker.last.update(outcome="never_called", at=None, model=None, detail=None, http_status=None, elapsed_ms=None)
    yield
    groq._tracker.clear_cooldown()


def patch_client(monkeypatch, handler, key="gsk_test"):
    real = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(groq.httpx, "Client", factory)
    if key:
        monkeypatch.setenv("GROQ_API_KEY", key)


def chat(content, finish="stop", model="qwen/qwen3.8-27b"):
    return {"model": model, "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}]}


def test_request_shape_and_success(monkeypatch):
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=chat('{"candidates": [{"quote": "اقرأ باسم ربك", "reference_text": "العلق: 1"}]}'))

    patch_client(monkeypatch, handler)
    p = groq.GroqProvider()
    out = p.extract("مقال")
    assert [(s.quote, s.reference_text) for s in out] == [("اقرأ باسم ربك", "العلق: 1")]
    assert seen["auth"] == "Bearer gsk_test" and "gsk_test" not in seen["url"]
    body = seen["body"]
    assert seen["url"] == groq.ENDPOINT
    rf = body["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    items = rf["json_schema"]["schema"]["properties"]["candidates"]["items"]
    assert items["additionalProperties"] is False and set(items["required"]) == {"quote", "reference_text"}
    assert body["temperature"] == 0 and body["reasoning_effort"] == "none"
    assert "<article>" in body["messages"][1]["content"]
    st = groq.last_call_status()
    assert st["outcome"] == "ok" and st["http_status"] == 200 and st["elapsed_ms"] is not None


def test_non_qwen_model_omits_reasoning_effort(monkeypatch):
    monkeypatch.setattr(groq, "settings", dataclasses.replace(groq.settings, groq_model="openai/gpt-oss-20b"))
    assert "reasoning_effort" not in groq.build_request("openai/gpt-oss-20b", "x")


@pytest.mark.parametrize(
    "status,match",
    [(429, "الحصة"), (503, "503"), (498, "498"), (500, "500"), (401, "مرفوض"), (400, "400"), (404, "404")],
)
def test_http_errors_make_exactly_one_call(monkeypatch, status, match):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json={"error": {"message": "x", "type": "y"}})

    patch_client(monkeypatch, handler)
    with pytest.raises(ExtractionError, match=match):
        groq.GroqProvider().extract("مقال")
    assert len(calls) == 1  # no retry chain: quota is not burned
    st = groq.last_call_status()
    assert st["outcome"] == "failed" and st["http_status"] == status and st["cooldown_seconds"] > 0


@pytest.mark.parametrize(
    "payload",
    [
        chat("not json at all"),
        chat('{"foo": 1}'),
        chat('{"candidates": []', finish="length"),
        {"choices": []},
        {"choices": [{"message": {"content": None}}]},
    ],
)
def test_malformed_or_truncated_output(monkeypatch, payload):
    patch_client(monkeypatch, lambda r: httpx.Response(200, json=payload))
    with pytest.raises(ExtractionError):
        groq.GroqProvider().extract("مقال")
    assert groq.last_call_status()["outcome"] == "failed"


def test_timeout_and_cooldown(monkeypatch):
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("slow", request=request)

    patch_client(monkeypatch, handler)
    with pytest.raises(ExtractionError, match="مهلة"):
        groq.GroqProvider().extract("مقال")
    with pytest.raises(ExtractionError, match="مؤقتًا"):
        groq.GroqProvider().extract("مقال")
    assert len(calls) == 1  # second audit skipped the network during the cooldown


def test_no_key_unavailable(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert groq.GroqProvider().available() is False


@pytest.mark.parametrize(
    "selection,keys,expected",
    [
        ("auto", {"GROQ_API_KEY": "g", "GEMINI_API_KEY": "m"}, "groq"),
        ("auto", {"GEMINI_API_KEY": "m"}, "gemini"),
        ("auto", {}, None),
        ("gemini", {"GROQ_API_KEY": "g", "GEMINI_API_KEY": "m"}, "gemini"),
        ("groq", {"GEMINI_API_KEY": "m"}, None),  # explicit choice never silently switches provider
        ("none", {"GROQ_API_KEY": "g"}, None),
    ],
)
def test_provider_selection(monkeypatch, selection, keys, expected):
    for k in ("GROQ_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for k, v in keys.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(base, "settings", dataclasses.replace(base.settings, ai_provider=selection))
    p = base.configured_provider()
    assert (p.name if p else None) == expected


def test_invented_text_is_discarded_end_to_end(use_source, monkeypatch):
    """A real provider object with a mocked HTTP answer: invented quotes never become findings."""
    article = "قال تعالى وتعاونوا على البر والتقوى في كتابه."
    content = json.dumps({"candidates": [
        {"quote": "وتعاونوا على البر والتقوى", "reference_text": ""},
        {"quote": "إن الله مع الصابرين", "reference_text": "البقرة: 153"},  # not in the article
    ]}, ensure_ascii=False)
    patch_client(monkeypatch, lambda r: httpx.Response(200, json=chat(content)))
    monkeypatch.setattr(audit, "get_provider", lambda: groq.GroqProvider())
    res = audit.run_audit(article)
    assert res["mode"] == "ai"
    assert res["ai"]["responded"] and res["ai"]["proposed"] == 2 and res["ai"]["located"] == 1 and res["ai"]["discarded"] == 1
    assert [f["quote"] for f in res["findings"]] == ["وتعاونوا على البر والتقوى"]
    for f in res["findings"]:
        assert article[f["start"]:f["end"]] == f["quote"]


def test_ai_failure_record_in_audit(use_source, monkeypatch):
    patch_client(monkeypatch, lambda r: httpx.Response(503, json={}))
    monkeypatch.setattr(audit, "get_provider", lambda: groq.GroqProvider())
    res = audit.run_audit("قال تعالى: ﴿اقرأ باسم ربك الذي خلق﴾ [العلق: 1]")
    assert res["mode"] == "ai_failed"
    assert res["ai"]["responded"] is False and res["ai"]["outcome"] == "failed" and res["ai"]["http_status"] == 503
    assert res["findings"][0]["wording"]["status"] == "matched"  # deterministic path still works


def test_health_distinguishes_configured_from_responded(use_source, monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main

    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setattr(main, "get_provider", lambda: groq.GroqProvider())
    h = TestClient(main.app).get("/api/health").json()
    assert h["ai_configured"] is True and h["provider_name"] == "groq"
    assert h["ai_last_call"]["outcome"] == "never_called"
    assert "gsk_test" not in json.dumps(h)


def test_prompt_version_default_and_override(monkeypatch):
    from app.extraction import prompts
    assert prompts.prompt_version() == "v2"
    assert groq.build_request("m", "مقال")["messages"][0]["content"] == prompts.PROMPTS["v2"]
    monkeypatch.setattr(prompts, "settings", dataclasses.replace(prompts.settings, extraction_prompt="v1"))
    assert groq.build_request("m", "مقال")["messages"][0]["content"] == prompts.PROMPTS["v1"]
    monkeypatch.setattr(prompts, "settings", dataclasses.replace(prompts.settings, extraction_prompt="nope"))
    assert prompts.prompt_version() == "v2"
