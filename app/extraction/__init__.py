"""Candidate quotation extraction.

Extraction only proposes *where* a Quran quotation may be. It never decides
what the correct Quran text is; that is the verifier's job, using Quranpedia.
"""

from .base import Candidate, ExtractionError, ExtractionProvider, get_provider

__all__ = ["Candidate", "ExtractionError", "ExtractionProvider", "get_provider"]
