"""Quranpedia Hafs text: fetching, caching and search index.

Source: Quranpedia API v1, mushaf 1 (Hafs ʿan ʿĀṣim)
        https://api.quranpedia.net/v1/mushafs/1
Policy: https://quranpedia.net/api-docs#usage-policy

Usage-policy notes that shaped this module:

* The whole Hafs text is fetched with **one** documented request (the
  mushaf endpoint) instead of crawling thousands of per-ayah endpoints.
* It is kept in memory and in a local temporary file for ``CACHE_TTL``
  (24 h, matching the API's own ``Cache-Control: max-age=86400``) so that
  corrections published by Quranpedia reach users within a day.
* Both caches are **per process / per machine**. On serverless hosts such as
  Vercel the temporary directory belongs to one function instance and is
  discarded with it, so every new (cold) instance fetches the text again and
  the stale fallback only helps an instance that had already loaded the text.
* The text is never committed to Git, exported or re-published by this app.
* When the source cannot be reached and no recent cache exists, the app
  reports the source as unavailable. It never falls back to AI-generated
  or hard-coded Quran text.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from . import arabic
from .config import settings

log = logging.getLogger(__name__)

API_BASE = "https://api.quranpedia.net/v1"
MUSHAF_ID = 1  # Hafs
MUSHAF_URL = f"{API_BASE}/mushafs/{MUSHAF_ID}"
CACHE_TTL = 24 * 3600
STALE_LIMIT = 7 * 24 * 3600
FAILURE_BACKOFF = 60


def ayah_api_url(surah: int, ayah: int) -> str:
    return f"{API_BASE}/mushafs/{MUSHAF_ID}/{surah}/{ayah}"


def ayah_page_url(surah: int, ayah: int) -> str:
    return f"https://api.quranpedia.net/embed?surah={surah}&ayah={ayah}"


class SourceUnavailable(Exception):
    """Raised when the Quran text cannot be obtained from Quranpedia."""


@dataclass
class Ayah:
    surah: int
    number: int
    text: str  # canonical text as served (BOM stripped)
    words: list[str]  # canonical words, annotation marks removed
    folded: list[str]  # folded words, parallel to ``words``


@dataclass
class QuranIndex:
    ayahs: dict[tuple[int, int], Ayah]
    # Per surah: flat stream of (folded word, ayah number, word index in ayah)
    streams: dict[int, list[tuple[str, int, int]]]
    # folded word -> [(surah, position in stream)]
    positions: dict[str, list[tuple[int, int]]]
    # folded word -> number of ayahs containing it (for weighting)
    doc_freq: dict[str, int]
    # (surah, ayah) -> (first, last+1) position in the surah stream
    ayah_pos: dict[tuple[int, int], tuple[int, int]]
    fetched_at: float
    stale: bool = False
    loaded_from: str = "network"  # "network" or "disk" (temporary file on this machine)
    notes: list[str] = field(default_factory=list)

    @property
    def ayah_count(self) -> int:
        return len(self.ayahs)


def _split_words(text: str) -> tuple[list[str], list[str]]:
    words: list[str] = []
    folds: list[str] = []
    for piece in arabic.literal(text).split(" "):
        f = arabic.folded(piece)
        if f:
            words.append(piece)
            folds.append(f)
    return words, folds


def build_index(raw_ayahs: list[dict], fetched_at: float) -> QuranIndex:
    """Build the index from records of the form {surah, number, text}."""
    ayahs: dict[tuple[int, int], Ayah] = {}
    streams: dict[int, list[tuple[str, int, int]]] = defaultdict(list)
    positions: dict[str, list[tuple[int, int]]] = defaultdict(list)
    doc_freq: dict[str, int] = defaultdict(int)
    ayah_pos: dict[tuple[int, int], tuple[int, int]] = {}
    for rec in sorted(raw_ayahs, key=lambda r: (int(r["surah"]), int(r["number"]))):
        s, n = int(rec["surah"]), int(rec["number"])
        text = str(rec["text"]).replace("﻿", "").strip()
        words, folds = _split_words(text)
        ayahs[(s, n)] = Ayah(s, n, text, words, folds)
        for w in set(folds):
            doc_freq[w] += 1
        stream = streams[s]
        ayah_pos[(s, n)] = (len(stream), len(stream) + len(folds))
        for i, f in enumerate(folds):
            positions[f].append((s, len(stream)))
            stream.append((f, n, i))
    # No phrase index is kept: phrase search (app/phrases.py) walks ``streams`` from ``positions``,
    # which saves the ~21 MB a dictionary of every 4-word sequence used to take.
    return QuranIndex(dict(ayahs), dict(streams), dict(positions), dict(doc_freq), ayah_pos, fetched_at)


def _flatten_mushaf(payload: dict) -> list[dict]:
    """Validate the mushaf payload and flatten to [{surah, number, text}]."""
    if not isinstance(payload, dict) or not isinstance(payload.get("surahs"), list):
        raise SourceUnavailable("unexpected response shape from Quranpedia")
    out: list[dict] = []
    for surah in payload["surahs"]:
        sid = int(surah["id"])
        for a in surah.get("ayahs") or []:
            text = a.get("text")
            if not isinstance(text, str) or not text.strip():
                raise SourceUnavailable("empty ayah text in Quranpedia response")
            out.append({"surah": sid, "number": int(a["number"]), "text": text})
    if len(payload["surahs"]) != 114 or len(out) != 6236:
        raise SourceUnavailable(f"incomplete Hafs text from Quranpedia ({len(out)} ayahs)")
    return out


class QuranSource:
    """Thread-safe lazy loader around the Quranpedia mushaf endpoint."""

    def __init__(self, cache_dir: str | None = None, fetcher=None):
        self._lock = threading.Lock()
        self._index: QuranIndex | None = None
        self._last_failure = 0.0
        self._last_error: str | None = None
        self.cache_path = Path(cache_dir or os.path.join(tempfile.gettempdir(), "quran-auditor-cache")) / "hafs-mushaf-1.json"
        self._fetcher = fetcher or self._fetch_remote
        self.started_at = time.time()

    # -- public -----------------------------------------------------------
    def get(self) -> QuranIndex:
        """Return a fresh-enough index or raise ``SourceUnavailable``."""
        now = time.time()
        idx = self._index
        if idx and not idx.stale and now - idx.fetched_at < CACHE_TTL:
            return idx
        with self._lock:
            idx = self._index
            if idx and not idx.stale and now - idx.fetched_at < CACHE_TTL:
                return idx
            if not idx:
                idx = self._load_disk()
                if idx and now - idx.fetched_at < CACHE_TTL:
                    self._index = idx
                    return idx
            if now - self._last_failure > FAILURE_BACKOFF:
                try:
                    records = self._fetcher()
                    fresh = build_index(records, time.time())
                    self._index = fresh
                    self._save_disk(records, fresh.fetched_at)
                    self._last_error = None
                    return fresh
                except Exception as exc:  # network, HTTP, JSON or shape errors
                    self._last_failure = now
                    self._last_error = type(exc).__name__
                    log.warning("Quranpedia fetch failed: %s", type(exc).__name__)
            if idx and now - idx.fetched_at < STALE_LIMIT:
                idx.stale = True
                if not idx.notes:
                    age_h = int((now - idx.fetched_at) // 3600)
                    idx.notes.append(f"تعذّر تحديث النص من قرآنبيديا؛ استُخدمت نسخة مخبأة على هذا الخادم عمرها نحو {age_h} ساعة.")
                self._index = idx
                return idx
            raise SourceUnavailable(self._last_error or "source unavailable")

    def status(self) -> dict:
        idx = self._index
        return {
            "loaded": idx is not None,
            "loaded_from": idx.loaded_from if idx else None,
            "fetched_at": idx.fetched_at if idx else None,
            "age_seconds": int(time.time() - idx.fetched_at) if idx else None,
            "stale": bool(idx and idx.stale),
            "ayahs": idx.ayah_count if idx else 0,
            "last_error": self._last_error,
            "instance_started": self.started_at,
        }

    # -- internals --------------------------------------------------------
    def _fetch_remote(self) -> list[dict]:
        """One request; a single retry only for transient network/5xx errors."""
        headers = {"User-Agent": settings.user_agent, "Accept": "application/json"}
        with httpx.Client(timeout=httpx.Timeout(settings.source_timeout, connect=8.0), headers=headers, follow_redirects=True) as client:
            for attempt in (1, 2):
                try:
                    resp = client.get(MUSHAF_URL)
                    if resp.status_code >= 500 and attempt == 1:
                        time.sleep(1.0)
                        continue
                    resp.raise_for_status()
                    return _flatten_mushaf(resp.json())
                except (httpx.TimeoutException, httpx.TransportError):
                    if attempt == 2:
                        raise
                    time.sleep(1.0)
        raise SourceUnavailable("unreachable")

    def _load_disk(self) -> QuranIndex | None:
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            fetched_at = float(data["fetched_at"])
            if time.time() - fetched_at > STALE_LIMIT:
                return None
            idx = build_index(data["ayahs"], fetched_at)
            idx.loaded_from = "disk"
            return idx
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _save_disk(self, records: list[dict], fetched_at: float) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"fetched_at": fetched_at, "source": MUSHAF_URL, "ayahs": records}, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.cache_path)
        except OSError:
            log.info("Could not write Quran cache; continuing with memory cache only")


source = QuranSource(cache_dir=settings.cache_dir)
