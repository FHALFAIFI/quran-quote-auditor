"""Audit pipeline: extract candidates → locate in article → attach references → verify."""

from __future__ import annotations

import time

from . import arabic
from .config import settings
from .extraction import Candidate, ExtractionError, get_provider
from .extraction.marked import extract_marked
from .quran_source import MUSHAF_URL, NGRAM, QuranIndex, SourceUnavailable, source
from .references import Reference, find_references
from .verifier import script_diff_kind, source_word, unavailable_result, verify

SCAN_MIN_WORDS = 5
REF_AFTER_CHARS, REF_AFTER_WORDS = 40, 3
REF_BEFORE_CHARS, REF_BEFORE_WORDS = 60, 6
PRIORITY = {"marked": 0, "ai": 1, "scan": 2}


class InputError(ValueError):
    """Invalid user input; message is safe to show."""


def locate(tokens: list[arabic.Token], quote: str) -> list[tuple[int, int]]:
    """Token-index ranges [i, j) where ``quote`` occurs in the article (folded)."""
    qf = [t.fold for t in arabic.tokenize(quote)]
    if not qf:
        return []
    af = [t.fold for t in tokens]
    n = len(qf)
    return [(i, i + n) for i in range(len(af) - n + 1) if af[i:i + n] == qf]


def scan_index(tokens: list[arabic.Token], index: QuranIndex) -> list[tuple[int, int]]:
    """Unmarked runs of ≥ SCAN_MIN_WORDS article words that occur verbatim (folded) in the Quran.

    Edge words whose letters differ significantly from the source (e.g. إن
    for أن) are trimmed, so ordinary prose next to a quotation is not absorbed.
    """
    af = [t.fold for t in tokens]

    def ok(ti: int, s: int, p: int) -> bool:
        src = source_word(index, s, p)
        return arabic.letters(tokens[ti].raw) == arabic.letters(src) or script_diff_kind(tokens[ti].raw, src) == "benign"

    runs: list[tuple[int, int]] = []
    i = 0
    while i <= len(af) - NGRAM:
        best = (0, 0)  # (length, start offset after trimming)
        for s, p in index.ngrams.get(tuple(af[i:i + NGRAM]), []):
            stream = index.streams[s]
            k = NGRAM
            while i + k < len(af) and p + k < len(stream) and af[i + k] == stream[p + k][0]:
                k += 1
            lo, hi = 0, k
            while lo < hi and not ok(i + lo, s, p + lo):
                lo += 1
            while hi > lo and not ok(i + hi - 1, s, p + hi - 1):
                hi -= 1
            if hi - lo > best[0]:
                best = (hi - lo, lo)
        length, lo = best
        if length >= SCAN_MIN_WORDS:
            runs.append((i + lo, i + lo + length))
            i += lo + length
        else:
            i += 1
    return runs


def _span_candidate(article: str, tokens: list[arabic.Token], i: int, j: int, src: str) -> Candidate:
    s, e = tokens[i].start, tokens[j - 1].end
    return Candidate(s, e, article[s:e], {src})


def merge(cands: list[Candidate]) -> list[Candidate]:
    """Keep non-overlapping candidates, preferring marked > ai > scan; record agreeing sources."""
    kept: list[Candidate] = []
    for c in sorted(cands, key=lambda c: (min(PRIORITY[x] for x in c.sources), c.start, -(c.end - c.start))):
        overlap = next((k for k in kept if c.start < k.end and k.start < c.end), None)
        if overlap is None:
            kept.append(c)
        else:
            overlap.sources |= c.sources
            overlap.reference_hint = overlap.reference_hint or c.reference_hint
    return sorted(kept, key=lambda c: c.start)


def _words_between(article: str, a: int, b: int) -> int:
    return len(arabic.tokenize(article[a:b])) if b > a else 0


def attach_references(article: str, cands: list[Candidate], refs: list[Reference]) -> list[Reference | None]:
    """Associate each candidate with at most one nearby reference."""
    used: set[int] = set()
    out: list[Reference | None] = [None] * len(cands)
    free = [r for r in refs if not any(c.start <= r.start and r.end <= c.end for c in cands)]
    # 1) references right after the quotation
    for ci, c in enumerate(cands):
        limit = cands[ci + 1].start if ci + 1 < len(cands) else len(article)
        for ri, r in enumerate(free):
            if ri in used or r.start < c.end or r.start >= limit:
                continue
            if r.start - c.end <= REF_AFTER_CHARS and _words_between(article, c.end, r.start) <= REF_AFTER_WORDS:
                out[ci] = r
                used.add(ri)
            break
    # 2) reference text proposed by the AI, if it is really in the article near the quote
    for ci, c in enumerate(cands):
        if out[ci] is not None or not c.reference_hint:
            continue
        hint = arabic.folded(c.reference_hint)
        for ri, r in enumerate(free):
            if ri not in used and abs(r.start - c.end) <= 150 and hint and (hint in arabic.folded(r.text) or arabic.folded(r.text) in hint):
                out[ci] = r
                used.add(ri)
                break
    # 3) references just before the quotation ("في سورة البقرة: ...")
    for ci, c in enumerate(cands):
        if out[ci] is not None:
            continue
        floor = cands[ci - 1].end if ci > 0 else 0
        for ri in range(len(free) - 1, -1, -1):
            r = free[ri]
            if ri in used or r.end > c.start or r.end < floor:
                continue
            if c.start - r.end <= REF_BEFORE_CHARS and _words_between(article, r.end, c.start) <= REF_BEFORE_WORDS:
                out[ci] = r
                used.add(ri)
            break
    return out


def _line_col(article: str, pos: int) -> tuple[int, int]:
    line = article.count("\n", 0, pos) + 1
    col = pos - (article.rfind("\n", 0, pos) + 1) + 1
    return line, col


def run_audit(article: str) -> dict:
    if not isinstance(article, str) or not article.strip():
        raise InputError("الرجاء إدخال نص المقال.")
    article = article.replace("\r\n", "\n").replace("\r", "\n")
    if len(article) > settings.max_chars:
        raise InputError(f"النص أطول من الحد المسموح ({settings.max_chars} حرف).")
    started = time.monotonic()
    notices: list[dict] = []
    tokens = arabic.tokenize(article)
    refs = find_references(article)

    # Source first: without it nothing can be verified, but extraction still runs.
    index: QuranIndex | None
    try:
        index = source.get()
        if index.stale:
            notices.extend({"level": "warning", "text": n} for n in index.notes)
    except SourceUnavailable:
        index = None
        notices.append({"level": "error", "text": "تعذّر الوصول إلى قرآنبيديا الآن، فلن يُحكم على أي اقتباس. أعد المحاولة لاحقًا."})

    provider = get_provider()
    mode = "ai" if provider else "reduced"
    candidates: list[Candidate] = extract_marked(article, refs)
    discarded = 0
    if provider:
        try:
            for sug in provider.extract(article):
                spans = locate(tokens, sug.quote)
                if not spans:
                    discarded += 1
                    continue
                for i, j in spans:
                    c = _span_candidate(article, tokens, i, j, "ai")
                    c.reference_hint = sug.reference_text
                    candidates.append(c)
        except ExtractionError as exc:
            mode = "ai_failed"
            notices.append({"level": "warning", "text": f"تعذّر الاستخراج بالذكاء الاصطناعي ({exc}). عُرضت الاقتباسات المعلَّمة صراحةً والمقاطع المطابقة حرفيًا لنص المصحف فقط."})
    if discarded:
        notices.append({"level": "info", "text": f"استُبعد {discarded} مقطعًا اقترحه نموذج الذكاء الاصطناعي لأنه غير موجود حرفيًا في المقال."})
    if index is not None:
        for i, j in scan_index(tokens, index):
            candidates.append(_span_candidate(article, tokens, i, j, "scan"))

    candidates = [c for c in merge(candidates)][: settings.max_candidates]
    attached = attach_references(article, candidates, refs)

    findings = []
    for n, (c, ref) in enumerate(zip(candidates, attached), start=1):
        words = [t.raw for t in arabic.tokenize(c.text)]
        result = verify(index, words, ref) if index is not None else unavailable_result(ref)
        line, col = _line_col(article, c.start)
        findings.append({
            "id": n,
            "start": c.start,
            "end": c.end,
            "line": line,
            "column": col,
            "quote": c.text,
            "detected_by": sorted(c.sources, key=lambda x: PRIORITY[x]),
            "marker": c.marker,
            **result,
        })

    stats = {
        "total": len(findings),
        "matched": sum(f["wording"]["status"] == "matched" for f in findings),
        "difference": sum(f["wording"]["status"] == "difference" for f in findings),
        "uncertain": sum(f["wording"]["status"] == "uncertain" for f in findings),
        "needs_review": sum(f["needs_review"] for f in findings),
        "ref_matched": sum(f["reference"]["status"] == "matched" for f in findings),
        "ref_missing": sum(f["reference"]["status"] == "missing" for f in findings),
        "ref_incorrect": sum(f["reference"]["status"] == "incorrect" for f in findings),
        "ref_uncertain": sum(f["reference"]["status"] == "uncertain" for f in findings),
    }
    return {
        "mode": mode,
        "provider": provider.label if provider else None,
        "provider_model": provider.used_model if provider else None,
        "notices": notices,
        "source": {
            "name": "Quranpedia — مصحف حفص عن عاصم",
            "url": MUSHAF_URL,
            "available": index is not None,
            "fetched_at": index.fetched_at if index else None,
            "stale": bool(index and index.stale),
            "loaded_from": index.loaded_from if index else None,
        },
        "findings": findings,
        "stats": stats,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }
