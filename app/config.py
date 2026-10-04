"""Runtime configuration, read from environment variables only.

Secrets (``GEMINI_API_KEY``, ``GROQ_API_KEY``) are never read from files in the repository and
never written to logs or responses.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # auto: Groq if GROQ_API_KEY is set, else Gemini if GEMINI_API_KEY is set, else no AI.
    # One provider is used per audit; there is no cross-provider fallback chain.
    ai_provider: str = os.environ.get("AI_PROVIDER", "auto").strip().lower()
    groq_model: str = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b").strip()
    # "" = send "none" for qwen/ models only; "omit" = never send; or low/medium/high/none/default
    groq_reasoning_effort: str = os.environ.get("GROQ_REASONING_EFFORT", "").strip().lower()
    # Groq reserves output tokens per request against the account's 1,000 output-tokens/minute limit for this model. The default
    # was 4096 until 4 Oct 2026; the live service had no override and every live call that evening was refused (HTTP 429 OTPM), while
    # 75 of 76 local calls at 800 answered. The largest answer measured that evening used 341 output tokens (an 11-quotation article).
    groq_max_completion_tokens: int = _int("GROQ_MAX_COMPLETION_TOKENS", 800)
    extraction_prompt: str = os.environ.get("EXTRACTION_PROMPT", "v2").strip().lower()  # see app/extraction/prompts.py
    gemini_model: str = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip()
    gemini_fallback_models: tuple[str, ...] = tuple(m.strip() for m in os.environ.get("GEMINI_FALLBACK_MODELS", "").split(",") if m.strip())
    ai_timeout: float = _float("AI_TIMEOUT_SECONDS", 12.0)  # total AI budget per audit (Groq: its single attempt)
    ai_attempt_timeout: float = _float("AI_ATTEMPT_TIMEOUT_SECONDS", 8.0)  # cap per request
    ai_cooldown: float = _float("AI_COOLDOWN_SECONDS", 60.0)  # skip AI this long after a failure
    source_timeout: float = _float("SOURCE_TIMEOUT_SECONDS", 20.0)
    max_chars: int = _int("MAX_ARTICLE_CHARS", 20000)
    # The model is asked about an article only up to this length (Groq's free tier refuses large requests: see docs/TEST_LOG.md);
    # a longer article is still audited in full, by markers and by the search of the Quran text, without the model.
    ai_max_chars: int = _int("AI_MAX_ARTICLE_CHARS", 6000)
    max_candidates: int = _int("MAX_CANDIDATES", 150)
    rate_limit_per_minute: int = _int("RATE_LIMIT_PER_MINUTE", 10)
    suggest_rate_limit_per_minute: int = _int("SUGGEST_RATE_LIMIT_PER_MINUTE", 240)
    cache_dir: str | None = os.environ.get("QURAN_CACHE_DIR") or None
    contact: str = os.environ.get("QURANPEDIA_CONTACT", "").strip()

    @property
    def user_agent(self) -> str:
        ua = "quran-quote-auditor/0.1 (live verification tool; no bulk download)"
        return f"{ua} contact:{self.contact}" if self.contact else ua


settings = Settings()


def gemini_api_key() -> str | None:
    """Read the key at call time so it is never stored on module objects."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    return key or None


def groq_api_key() -> str | None:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    return key or None
