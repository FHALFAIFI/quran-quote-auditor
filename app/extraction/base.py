"""Provider interface for AI candidate extraction.

To add a provider, subclass :class:`ExtractionProvider`, implement
``extract`` and register it in ``_PROVIDERS``. Select it with the
``AI_PROVIDER`` environment variable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..config import settings


@dataclass
class Candidate:
    """A span of the submitted article that may contain a Quran quotation."""

    start: int
    end: int
    text: str
    sources: set[str] = field(default_factory=set)  # "ai", "marked", "phrase", "manual"
    marker: str | None = None  # e.g. "﴿﴾", "{}", "«»"
    reference_hint: str | None = None  # reference text proposed by the AI
    phrase: object | None = None  # the app.phrases.PhraseHit that found this span, if any


@dataclass
class RawSuggestion:
    """Untrusted provider output before it is located in the article."""

    quote: str
    reference_text: str | None = None


class ExtractionError(Exception):
    """Provider failed (timeout, HTTP error, malformed output). Message is safe to show."""


class ExtractionProvider(ABC):
    name: str = "base"
    label: str = "base"
    used_model: str | None = None  # model that actually answered the last call, if relevant
    tracker = None  # CallTracker with the outcome of this provider's last real call

    @abstractmethod
    def available(self) -> bool:
        """True if the provider is configured (e.g. has an API key)."""

    @abstractmethod
    def extract(self, article: str) -> list[RawSuggestion]:
        """Return candidate quotations copied verbatim from ``article``."""


def _registry() -> dict[str, type[ExtractionProvider]]:
    from .gemini import GeminiProvider
    from .groq import GroqProvider

    return {"groq": GroqProvider, "gemini": GeminiProvider}


def configured_provider() -> ExtractionProvider | None:
    """The provider selected by AI_PROVIDER that has a key configured, or None.

    ``auto`` (default) picks Groq when GROQ_API_KEY is set, else Gemini when
    GEMINI_API_KEY is set. Exactly one provider is used; if it fails the audit
    falls back to deterministic extraction, not to another model.
    """
    name = settings.ai_provider
    if name in ("", "none", "off"):
        return None
    registry = _registry()
    order = list(registry) if name == "auto" else [name]
    for n in order:
        cls = registry.get(n)
        if cls is None:
            continue
        provider = cls()
        if provider.available():
            return provider
    return None


def get_provider() -> ExtractionProvider | None:
    return configured_provider()
