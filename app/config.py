"""Runtime configuration, read from environment variables only.

Secrets (``GEMINI_API_KEY``) are never read from files in the repository and
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
    ai_provider: str = os.environ.get("AI_PROVIDER", "gemini").strip().lower()
    gemini_model: str = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip()
    gemini_fallback_models: tuple[str, ...] = tuple(m.strip() for m in os.environ.get("GEMINI_FALLBACK_MODELS", "").split(",") if m.strip())
    ai_timeout: float = _float("AI_TIMEOUT_SECONDS", 12.0)  # total budget for all Gemini attempts
    ai_attempt_timeout: float = _float("AI_ATTEMPT_TIMEOUT_SECONDS", 8.0)  # cap per request
    ai_cooldown: float = _float("AI_COOLDOWN_SECONDS", 60.0)  # skip AI this long after a failure
    source_timeout: float = _float("SOURCE_TIMEOUT_SECONDS", 20.0)
    max_chars: int = _int("MAX_ARTICLE_CHARS", 6000)
    max_candidates: int = _int("MAX_CANDIDATES", 40)
    rate_limit_per_minute: int = _int("RATE_LIMIT_PER_MINUTE", 10)
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
