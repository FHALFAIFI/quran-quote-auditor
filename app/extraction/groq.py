"""Groq provider (OpenAI-compatible Chat Completions with a strict JSON schema).

Docs checked 2026-09-29: https://console.groq.com/docs/structured-outputs,
https://console.groq.com/docs/reasoning, https://console.groq.com/docs/errors.
``qwen/qwen3.8-27b`` supports strict ``json_schema`` (constrained decoding) and
``reasoning_effort: "none"``. Groq lists it as a *preview* model.

As with Gemini, the model only points at candidate substrings. Its output is
untrusted: the pipeline re-locates every quote in the article and discards
anything that is not there. Quran text and verdicts never come from the model.

Quota discipline: one model, one attempt per audit, a bounded timeout, and a
cooldown after a failure. There is no model-fallback chain.
"""

from __future__ import annotations

import re
import time

import httpx

from ..config import groq_api_key, settings
from .base import ExtractionError, ExtractionProvider, ProviderCoolingDown, RawSuggestion
from .gemini import parse_model_json
from .prompts import system_prompt
from .status import CallTracker

ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

# Strict mode requires every property to be listed in "required" and
# additionalProperties to be false at every object level.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string", "description": "Verbatim substring of the article"},
                    "reference_text": {"type": "string", "description": "Verbatim nearby reference, or empty string"},
                },
                "required": ["quote", "reference_text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidates"],
    "additionalProperties": False,
}

_tracker = CallTracker()


def last_call_status() -> dict:
    return _tracker.status()


# Groq documents one 400 for a model-generation failure under strict structured outputs
# (console.groq.com/docs/structured-outputs, read 2026-10-01): "Generated JSON does not match the expected schema."
# Any other 400 means the request itself was refused and needs a code fix, not a retry.
_GENERATION_FAILURE_MARKERS = ("does not match the expected schema", "json_validate_failed")


# Identifiers of the service account that Groq writes into its messages (e.g. "in organization `org_01…`"), and anything
# shaped like a key: neither belongs in an answer sent to a public visitor.
_ACCOUNT_IDS = re.compile(r"\b(org|proj|user|gsk|sk)_[A-Za-z0-9_-]{6,}")


def _redact(text: str) -> str:
    return _ACCOUNT_IDS.sub(lambda m: m.group(1) + "_…", text)[:300]


def error_body(resp: httpx.Response) -> dict:
    """The provider's error object (type, code, param, message), shortened, with account ids redacted. Never contains the API key.

    ``failed_generation`` (Groq's copy of the model's rejected output under strict JSON) is NOT kept, only its length: it is
    model-generated text, so besides passages of the writer's article it may hold text that is not in the article at all
    (an invented or paraphrased verse, prompt fragments). It is never shown, logged, or put in the audit answer.
    """
    try:
        err = resp.json().get("error") or {}
    except (ValueError, AttributeError):
        err = {}
    if not isinstance(err, dict):
        err = {"message": str(err)}
    body: dict = {k: (_redact(str(err[k])) if err.get(k) is not None else None) for k in ("type", "code", "param", "message")}
    if err.get("failed_generation") is not None:
        body["failed_generation_chars"] = len(str(err["failed_generation"]))
    if not any(body.values()):
        body["raw"] = _redact(resp.text)
    return {k: v for k, v in body.items() if v is not None}


def _retry_after(resp: httpx.Response) -> float:
    """Seconds from a numeric ``retry-after`` header (0 when absent or not a number), capped at one hour."""
    try:
        return min(3600.0, max(0.0, float(resp.headers.get("retry-after", "0"))))
    except ValueError:
        return 0.0


def is_generation_failure(status: int, body: dict) -> bool:
    text = " ".join(str(v) for v in body.values()).lower()
    return status == 400 and any(m in text for m in _GENERATION_FAILURE_MARKERS)


def _reasoning_effort(model: str) -> str | None:
    """Only send reasoning_effort when configured or when the model is known to accept "none"."""
    configured = settings.groq_reasoning_effort
    if configured:
        return None if configured == "omit" else configured
    return "none" if model.startswith("qwen/") else None


def build_request(model: str, article: str) -> dict:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": "<article>\n" + article + "\n</article>"},
        ],
        "temperature": 0,
        "max_completion_tokens": settings.groq_max_completion_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "quran_quote_candidates", "strict": True, "schema": RESPONSE_SCHEMA},
        },
    }
    effort = _reasoning_effort(model)
    if effort:
        body["reasoning_effort"] = effort
    return body


class GroqProvider(ExtractionProvider):
    name = "groq"
    tracker = _tracker

    def __init__(self) -> None:
        self.model = settings.groq_model
        self.used_model = self.model
        self.label = f"Groq ({self.model})"

    def available(self) -> bool:
        return groq_api_key() is not None

    def extract(self, article: str) -> list[RawSuggestion]:
        key = groq_api_key()
        if not key:
            raise ExtractionError("مفتاح GROQ_API_KEY غير مضبوط")
        wait = _tracker.cooldown_remaining()
        if wait > 0:
            raise ProviderCoolingDown(wait)  # not a call: the audit says the model was not asked, not that it failed
        budget = max(2.0, settings.ai_timeout)
        started = time.monotonic()

        def ms() -> int:
            return int((time.monotonic() - started) * 1000)

        def fail(detail: str, message: str, status: int | None = None, cooldown: float | None = None, body: dict | None = None):
            _tracker.start_cooldown(settings.ai_cooldown if cooldown is None else cooldown)
            _tracker.record("failed", self.model, detail, status, ms())  # the tracker is public via /api/health: no body here
            raise ExtractionError(message, body=body, generation_failure=bool(body) and is_generation_failure(status or 0, body))

        try:
            with httpx.Client() as client:
                resp = client.post(
                    ENDPOINT,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=build_request(self.model, article),
                    timeout=httpx.Timeout(budget, connect=min(5.0, budget)),
                )
        except httpx.TimeoutException:
            fail("timeout", "انتهت مهلة خدمة الذكاء الاصطناعي")
        except httpx.HTTPError:
            fail("connection", "تعذّر الاتصال بخدمة الذكاء الاصطناعي")
        except Exception:  # an unexpected client-library error: still one attempt, a cooldown, and a source-based audit
            fail("error", "تعذّر الاتصال بخدمة الذكاء الاصطناعي")

        code = resp.status_code
        if code == 429:
            # never sooner than Groq's own retry-after (e.g. a daily limit), and never sooner than two minutes
            fail("429", "تجاوزت خدمة الذكاء الاصطناعي حد الاستخدام (الحصة) مؤقتًا", 429, max(settings.ai_cooldown, 120, _retry_after(resp)), error_body(resp))
        if code in (401, 403):
            fail(str(code), "مفتاح خدمة الذكاء الاصطناعي مرفوض (تحقق من GROQ_API_KEY)", code, max(settings.ai_cooldown, 300), error_body(resp))
        if code in (498, 503) or code >= 500:
            fail(str(code), f"خدمة الذكاء الاصطناعي مشغولة أو غير متاحة حاليًا ({code})", code, body=error_body(resp))
        if code >= 400:
            # 400: a strict-schema generation failure (body says so) or a refused request; 404: a retired model.
            fail(str(code), f"خدمة الذكاء الاصطناعي أعادت الخطأ {code}", code, body=error_body(resp))
        try:
            choice = resp.json()["choices"][0]
            text = choice["message"]["content"]
            if not isinstance(text, str):
                raise TypeError
        except (ValueError, KeyError, IndexError, TypeError):
            fail("empty_or_blocked", "استجابة خدمة الذكاء الاصطناعي غير مكتملة", code)
        if choice.get("finish_reason") == "length":
            fail("truncated", "استجابة خدمة الذكاء الاصطناعي مقطوعة (تجاوزت الطول)", code)
        try:
            suggestions = parse_model_json(text, settings.max_candidates)
        except ExtractionError:
            _tracker.start_cooldown(settings.ai_cooldown)
            _tracker.record("failed", self.model, "malformed_json", code, ms())
            raise
        self.used_model = resp.json().get("model") or self.model
        _tracker.clear_cooldown()
        _tracker.record("ok", self.used_model, None, code, ms())
        return suggestions
