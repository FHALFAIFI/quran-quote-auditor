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
    sources: set[str] = field(default_factory=set)  # "ai", "marked", "scan"
    marker: str | None = None  # e.g. "﴿﴾", "{}", "«»"
    reference_hint: str | None = None  # reference text proposed by the AI


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

    @abstractmethod
    def available(self) -> bool:
        """True if the provider is configured (e.g. has an API key)."""

    @abstractmethod
    def extract(self, article: str) -> list[RawSuggestion]:
        """Return candidate quotations copied verbatim from ``article``."""


def get_provider() -> ExtractionProvider | None:
    from .gemini import GeminiProvider

    providers: dict[str, type[ExtractionProvider]] = {"gemini": GeminiProvider}
    cls = providers.get(settings.ai_provider)
    if cls is None or settings.ai_provider in ("", "none", "off"):
        return None
    provider = cls()
    return provider if provider.available() else None
