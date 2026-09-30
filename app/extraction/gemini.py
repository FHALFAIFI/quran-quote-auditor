"""Gemini provider (REST ``generateContent`` with a JSON response schema).

The model is asked only to *point at* candidate quotations by copying them
verbatim from the article. Its output is treated as untrusted: every quote is
re-located in the article by the caller and discarded if it is not there.
"""

from __future__ import annotations

import json
import re
import time

import httpx

from ..config import gemini_api_key, settings
from .base import ExtractionError, ExtractionProvider, RawSuggestion
from .prompts import PROMPTS, system_prompt
from .status import CallTracker

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = PROMPTS["v1"]  # kept for callers and tests; requests use system_prompt()

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "candidates": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "quote": {"type": "STRING", "description": "Verbatim substring of the article"},
                    "reference_text": {"type": "STRING", "description": "Verbatim nearby reference, or empty"},
                },
                "required": ["quote"],
            },
        }
    },
    "required": ["candidates"],
}


def parse_model_json(text: str, limit: int) -> list[RawSuggestion]:
    """Parse and validate model output. Raises ExtractionError if malformed."""
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.S)
    if fence:
        cleaned = fence.group(1)
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ExtractionError("استجابة نموذج الذكاء الاصطناعي ليست JSON صالحًا") from exc
    if isinstance(data, list):
        data = {"candidates": data}
    items = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ExtractionError("استجابة نموذج الذكاء الاصطناعي لا تطابق المخطط المتوقع")
    out: list[RawSuggestion] = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        quote = item.get("quote")
        if not isinstance(quote, str) or not quote.strip() or len(quote) > 2000:
            continue
        ref = item.get("reference_text")
        ref = ref.strip() if isinstance(ref, str) and ref.strip() and len(ref) <= 200 else None
        out.append(RawSuggestion(quote=quote.strip(), reference_text=ref))
    return out


_tracker = CallTracker()
# Module-level aliases kept for callers and tests (same mutable objects).
_cooldown_until = _tracker.cooldown_until
_last = _tracker.last


def _record(outcome: str, model: str | None, detail: str | None = None, http_status: int | None = None) -> None:
    _tracker.record(outcome, model, detail, http_status)


def last_call_status() -> dict:
    return _tracker.status()


def _cooldown_remaining() -> int:
    return _tracker.cooldown_remaining()


def _start_cooldown(seconds: float) -> None:
    _tracker.start_cooldown(seconds)


class GeminiProvider(ExtractionProvider):
    name = "gemini"
    tracker = _tracker

    def __init__(self) -> None:
        self.model = settings.gemini_model
        self.used_model = self.model
        self.label = f"Google Gemini ({self.model})"

    def available(self) -> bool:
        return gemini_api_key() is not None

    def extract(self, article: str) -> list[RawSuggestion]:
        key = gemini_api_key()
        if not key:
            raise ExtractionError("مفتاح GEMINI_API_KEY غير مضبوط")
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt()}]},
            "contents": [{"role": "user", "parts": [{"text": "<article>\n" + article + "\n</article>"}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": RESPONSE_SCHEMA,
                "maxOutputTokens": 4096,
            },
        }
        # Fail fast after a recent failure so a live demo is not stuck waiting (per instance).
        wait = _cooldown_remaining()
        if wait > 0:
            raise ExtractionError(f"خدمة الذكاء الاصطناعي غير متاحة مؤقتًا بعد فشل حديث؛ ستُعاد المحاولة بعد {wait} ث")
        # Attempt plan within one overall budget (AI_TIMEOUT_SECONDS), each call capped at
        # AI_ATTEMPT_TIMEOUT_SECONDS: primary model; one retry of it only after a *fast* 503;
        # then configured fallback models. 429 (quota) is never retried.
        plan = [self.model, self.model] + [m for m in settings.gemini_fallback_models if m != self.model]
        deadline = time.monotonic() + settings.ai_timeout
        resp = None
        timed_out: set[str] = set()
        with httpx.Client() as client:
            for i, model in enumerate(plan):
                remaining = deadline - time.monotonic()
                if remaining < 2:
                    break
                if model in timed_out:
                    continue  # a model that just hung will not answer a retry in time
                if i == 1:
                    time.sleep(min(1.0, remaining - 1.5))
                    remaining = deadline - time.monotonic()
                attempt = min(remaining, settings.ai_attempt_timeout)
                try:
                    r = client.post(
                        ENDPOINT.format(model=model),
                        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                        json=body,
                        timeout=httpx.Timeout(attempt, connect=min(5.0, attempt)),
                    )
                except httpx.TimeoutException:
                    timed_out.add(model)
                    self.used_model = model
                    continue
                except httpx.HTTPError as exc:
                    _start_cooldown(settings.ai_cooldown)
                    _record("failed", model, "connection")
                    raise ExtractionError("تعذّر الاتصال بخدمة الذكاء الاصطناعي") from exc
                resp, self.used_model = r, model
                if r.status_code == 503 or (r.status_code == 404 and i >= 1):
                    continue  # overloaded / unavailable model: try the next step of the plan
                break
        if resp is None or resp.status_code == 503:
            _start_cooldown(settings.ai_cooldown)
            _record("failed", self.used_model, "timeout" if resp is None else "503", None if resp is None else 503)
            if resp is None:
                raise ExtractionError("انتهت مهلة خدمة الذكاء الاصطناعي")
            raise ExtractionError("خدمة الذكاء الاصطناعي مشغولة حاليًا (503)")
        if resp.status_code == 429:
            _start_cooldown(max(settings.ai_cooldown, 120))
            _record("failed", self.used_model, "429", 429)
            raise ExtractionError("تجاوزت خدمة الذكاء الاصطناعي حد الاستخدام (الحصة) مؤقتًا")
        if resp.status_code >= 400:
            _record("failed", self.used_model, str(resp.status_code), resp.status_code)
            raise ExtractionError(f"خدمة الذكاء الاصطناعي أعادت الخطأ {resp.status_code}")
        try:
            payload = resp.json()
            parts = payload["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            _record("failed", self.used_model, "empty_or_blocked")
            raise ExtractionError("استجابة خدمة الذكاء الاصطناعي غير مكتملة أو محجوبة") from exc
        try:
            suggestions = parse_model_json(text, settings.max_candidates)
        except ExtractionError:
            _record("failed", self.used_model, "malformed_json")
            raise
        _cooldown_until[0] = 0.0
        _record("ok", self.used_model, None, 200)
        return suggestions
