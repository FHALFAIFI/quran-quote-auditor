"""A recorded FAKE Groq for tests: no network, no real key, no model.

``FakeProvider.install`` replaces the ``httpx`` name inside a provider module (``app.extraction.groq`` or ``.gemini``) with a
copy whose ``Client`` uses an ``httpx.MockTransport``. Nothing else in the process is touched, so a test may still use the
real httpx (for example to talk to a local uvicorn). Every request the provider makes is recorded in ``requests``.

The answers copy the shape of Groq's real error bodies (console.groq.com/docs/errors and bodies seen in this project's
logs); the account id and limits in them are made up. Each body carries sentinel strings so a test can prove that the
body never reaches /api/health or a log line.
"""

from __future__ import annotations

import json
import types

import httpx

KEY = "gsk_TEST_SENTINEL_7f3a9c2e5b1d4f6a8c0e"          # set as GROQ_API_KEY / GEMINI_API_KEY; must never appear anywhere
ORG = "org_01hSENTINELORG9x8y7z"                          # Groq writes the account's organisation id into rate-limit messages
FG_MARK = "FAILED_GENERATION_SENTINEL"                    # inside failed_generation
INVENTED = "ولقد يسرنا القرآن للذكر فهل من مدكر"           # a verse NOT in the article, "generated" by the fake model

# A realistic article: a bracketed quotation with its reference, a bracketed quotation with a wrong reference, an unmarked
# distinctive (and slightly misquoted) quotation, and a short common phrase. The two prose fragments below are the writer's
# own words, which must never leave the audit answer.
PROSE = ("في مطلع الوحي قال تعالى", "وهذا أصل في العمل الجماعي المشترك")
ARTICLE = (f"{PROSE[0]}: ﴿اقرأ باسم ربك الذي خلق﴾ [العلق: 1]، وفي التوحيد: ﴿قل هو الله أحد﴾ [الإخلاص: 2].\n"
           f"ومن هنا قيل وتعاونوا على البر والتقوى ولا تعاونوا على الشر والعدوان {PROSE[1]}.\n"
           "وفي سورة الشرح: فإن مع العسر يسرا.")


def chat(content, finish="stop", model="qwen/qwen3.8-27b"):
    return {"id": "chatcmpl-fake", "object": "chat.completion", "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 12, "total_tokens": 912}}


def _err(message, type_, code=None, **extra):
    return {"error": {"message": message, "type": type_, **({"code": code} if code else {}), **extra}}


def _json(status, body, headers=None):
    return lambda req: httpx.Response(status, json=body, headers=headers or {})


def _raise(exc_type, message):
    def handler(req):
        raise exc_type(message, request=req)
    return handler


def _unexpected(req):
    # a client-library defect whose message quotes the request (article text and key): must not escape into logs or answers
    raise RuntimeError(f"unexpected failure while sending «{PROSE[1]}» with {KEY}")


RPM = _err(f"Rate limit reached for model `qwen/qwen3.8-27b` in organization `{ORG}` service tier `on_demand` on requests per "
           "minute (RPM): Limit 30, Used 30, Requested 1. Please try again in 2s. Need more tokens? Upgrade to Dev Tier today at "
           "https://console.groq.com/settings/billing", "requests", "rate_limit_exceeded")
RPD = _err(f"Rate limit reached for model `qwen/qwen3.8-27b` in organization `{ORG}` service tier `on_demand` on requests per "
           "day (RPD): Limit 1000, Used 1000, Requested 1. Please try again in 14m24s.", "requests", "rate_limit_exceeded")
TOO_LARGE = _err(f"Request too large for model `qwen/qwen3.8-27b` in organization `{ORG}` service tier `on_demand` on tokens per "
                 "minute (TPM): Limit 1000, Requested 1673, please reduce your message size and try again. Need more tokens? "
                 "Upgrade to Dev Tier today at https://console.groq.com/settings/billing", "tokens", "rate_limit_exceeded")
JSON_FAILED = _err("Generated JSON does not match the expected schema. Please adjust your prompt. See 'failed_generation' for more "
                   "details.", "invalid_request_error", "json_validate_failed",
                   # Groq returns the model's rejected output: it echoes the writer's article, and here also text NOT in it
                   failed_generation=f'{{"candidates": [{{"quote": "{PROSE[1]}", "reference_text": "{INVENTED} {FG_MARK}"')

# name -> (answer, the strings of the provider's body that must never reach /api/health or a log)
GROQ_ANSWERS = {
    "429_rate_limit_rpm": (_json(429, RPM, {"retry-after": "2"}), ["Rate limit reached", ORG]),
    "429_rate_limit_rpd": (_json(429, RPD, {"retry-after": "864"}), ["requests per day", ORG]),
    "429_request_too_large": (_json(429, TOO_LARGE, {"retry-after": "41"}), ["Request too large", ORG]),
    "timeout": (_raise(httpx.ReadTimeout, "The read operation timed out"), []),
    "connect_error": (_raise(httpx.ConnectError, "[Errno 61] Connection refused"), []),
    "500": (_json(500, _err("Internal Server Error SENTINEL500", "internal_server_error")), ["SENTINEL500"]),
    "502": (lambda req: httpx.Response(502, text="<html><body>502 Bad Gateway SENTINEL502</body></html>"), ["SENTINEL502"]),
    "503": (_json(503, _err("Service Unavailable SENTINEL503", "service_unavailable")), ["SENTINEL503"]),
    "401": (_json(401, _err("Invalid API Key SENTINEL401", "invalid_request_error", "invalid_api_key")), ["SENTINEL401"]),
    "malformed_json": (_json(200, chat('{candidates: [{"quote": "اقرأ باسم')), []),
    "truncated": (_json(200, chat('{"candidates": [{"quote": "اقرأ باسم ربك', finish="length")), []),
    "empty_choices": (_json(200, {"id": "x", "model": "qwen/qwen3.8-27b", "choices": []}), []),
    "content_null": (_json(200, chat(None)), []),
    "content_empty": (_json(200, chat("")), []),
    "400_json_validate_failed": (_json(400, JSON_FAILED), [FG_MARK, INVENTED, "expected schema"]),
    "unexpected_client_error": (_unexpected, ["unexpected failure while sending"]),
    "200_answered_nothing": (_json(200, chat('{"candidates": []}')), []),
    "200_spans_not_in_article": (_json(200, chat(json.dumps({"candidates": [
        {"quote": INVENTED, "reference_text": "القمر: 17"},
        {"quote": "إن الله مع الصابرين", "reference_text": "البقرة: 153"}]}, ensure_ascii=False))), []),
}


class FakeProvider:
    """Answers every request with one scenario and records what was sent."""

    def __init__(self, answer):
        self.answer = answer
        self.requests: list[dict] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append({"method": request.method, "url": str(request.url), "headers": dict(request.headers),
                              "json": json.loads(request.content or b"null")})
        return self.answer(request)

    def install(self, monkeypatch, module) -> "FakeProvider":
        real = httpx.Client
        handle = self._handle

        def client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handle)
            return real(*args, **kwargs)

        fake = types.SimpleNamespace(**{k: getattr(httpx, k) for k in dir(httpx) if not k.startswith("__")})
        fake.Client = client
        monkeypatch.setattr(module, "httpx", fake)
        return self


class Clock:
    """Stands in for the ``time`` module of app.extraction.status, so a test can move the cooldown clock forward."""

    def __init__(self):
        import time as _time
        self._time, self.offset = _time, 0.0

    def monotonic(self):
        return self._time.monotonic() + self.offset

    def time(self):
        return self._time.time()
