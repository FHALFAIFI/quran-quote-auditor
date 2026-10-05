"""Verification of one candidate quotation against the Quranpedia Hafs text.

Everything in this module is deterministic. The AI never contributes Quran
text or verdicts; it only proposes candidate spans upstream.

Wording statuses
    matched     – the quotation occurs in the source (a unique location, or a
                  location confirmed by the nearby reference). ``level`` says
                  how: ``literal``, ``diacritics`` (diacritics ignored) or
                  ``normalized`` (script variants folded).
    difference  – letters match a unique location but the diacritics conflict
                  (deterministic), or the closest verse differs in wording
                  (fuzzy, always flagged for human review).
    uncertain   – too short, found in several verses, not found, or the
                  source was unavailable.

Reference statuses: matched, missing, incorrect, uncertain.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

from . import arabic, uthmani
from .quran_source import QuranIndex, ayah_api_url, ayah_page_url
from .references import Reference
from .surahs import NAMES

MIN_WORDS = 3  # shorter quotations are never confirmed without a reference
FUZZY_ACCEPT = 0.6  # minimum similarity to propose a closest verse
MAX_LISTED = 5
FATHATAN, ALEF, ALEF_MAQSURA = "ً", "ا", "ى"


@dataclass
class Span:
    """A contiguous run of words in one surah stream: [p0, p1)."""

    surah: int
    p0: int
    p1: int


# ---------------------------------------------------------------------------
# index helpers
# ---------------------------------------------------------------------------

def find_exact(index: QuranIndex, qf: list[str], alts: list[tuple[str, ...]] | None = None) -> list[Span]:
    """All occurrences of the folded word sequence ``qf`` (may cross ayahs).

    ``alts[k]`` lists other folds word k may stand for (an Uthmani spelling the rasm does not settle, see
    ``uthmani.alternatives``); a place matches when every word equals its fold or one of its alternatives.
    """
    if not qf:
        return []
    n = len(qf)
    alts = alts if alts and any(alts) else None
    out: list[Span] = []
    seen: set[tuple[int, int]] = set()
    for first in (qf[0], *alts[0]) if alts else (qf[0],):
        for s, p in index.positions.get(first, []):
            if (s, p) in seen:
                continue
            stream = index.streams[s]
            if p + n <= len(stream) and all(stream[p + k][0] == qf[k] or (alts is not None and stream[p + k][0] in alts[k]) for k in range(n)):
                seen.add((s, p))
                out.append(Span(s, p, p + n))
    if alts:
        out.sort(key=lambda sp: (sp.surah, sp.p0))
    return out


def span_segments(index: QuranIndex, span: Span) -> list[dict]:
    """Per-ayah breakdown of a span: canonical words and the matched range."""
    stream = index.streams[span.surah]
    segs: list[dict] = []
    for p in range(span.p0, span.p1):
        _, ayah_no, wi = stream[p]
        if not segs or segs[-1]["ayah"] != ayah_no:
            ayah = index.ayahs[(span.surah, ayah_no)]
            segs.append({"surah": span.surah, "ayah": ayah_no, "words": ayah.words, "from": wi, "to": wi + 1, "text": ayah.text})
        else:
            segs[-1]["to"] = wi + 1
    return segs


def source_word(index: QuranIndex, surah: int, pos: int) -> str:
    _, ayah_no, wi = index.streams[surah][pos]
    return index.ayahs[(surah, ayah_no)].words[wi]


def span_words(index: QuranIndex, span: Span) -> list[str]:
    stream = index.streams[span.surah]
    return [index.ayahs[(span.surah, stream[p][1])].words[stream[p][2]] for p in range(span.p0, span.p1)]


def span_ayahs(index: QuranIndex, span: Span) -> tuple[int, int]:
    stream = index.streams[span.surah]
    return stream[span.p0][1], stream[span.p1 - 1][1]


def span_label(index: QuranIndex, span: Span) -> str:
    a0, a1 = span_ayahs(index, span)
    name = NAMES.get(span.surah, str(span.surah))
    return f"{name}: {a0}" if a0 == a1 else f"{name}: {a0}–{a1}"


def coverage(index: QuranIndex, span: Span) -> str:
    """'full' (whole ayah/ayahs), 'partial' (part of one ayah) or 'multi-partial'."""
    a0, a1 = span_ayahs(index, span)
    starts_at_ayah = index.ayah_pos[(span.surah, a0)][0] == span.p0
    ends_at_ayah = index.ayah_pos[(span.surah, a1)][1] == span.p1
    if starts_at_ayah and ends_at_ayah:
        return "full"
    return "partial" if a0 == a1 else "multi-partial"


# ---------------------------------------------------------------------------
# word-level comparison for exact (folded) matches
# ---------------------------------------------------------------------------

def _mark_profile(word: str) -> list[tuple[str, frozenset[str]]]:
    prof = [(b, set(m) - {"ٰ"}) for b, m in arabic.diacritic_profile(word)]
    # Tanween fath may be written on the final alef/alef maqsura or on the letter before it.
    if len(prof) >= 2 and prof[-1][0] in (ALEF, ALEF_MAQSURA) and FATHATAN in prof[-1][1]:
        prof[-1][1].discard(FATHATAN)
        prof[-2][1].add(FATHATAN)
    return [(b, frozenset(m)) for b, m in prof]


def diacritics_conflict(quote_word: str, source_word: str) -> bool:
    """True if the quote carries a diacritic that the source word does not have."""
    q, s = _mark_profile(quote_word), _mark_profile(source_word)
    if [b for b, _ in q] != [b for b, _ in s]:
        return False  # letters differ; handled as a script difference instead
    return any(not qm <= sm for (_, qm), (_, sm) in zip(q, s))


# Simplified spellings commonly typed for a source letter (quote char, source char).
# Anything else that folds together — e.g. إ written for أ — changes the word
# and is reported as a difference, not as a match.
_BENIGN = {
    ("ا", "أ"), ("ا", "إ"), ("ا", "آ"), ("ا", "ٱ"), ("أ", "ٱ"), ("إ", "ٱ"),
    ("ي", "ى"), ("ى", "ي"), ("ه", "ة"),
    ("و", "ؤ"), ("ي", "ئ"), ("ى", "ئ"),
}


def script_diff_kind(quote_word: str, source_word: str) -> str:
    """'uthmani' if the quote is a recognised Uthmani spelling of the source word, 'benign' if it only simplifies letter forms
    of the source, else 'significant'."""
    if uthmani.equivalent(quote_word, source_word):
        return "uthmani"
    q, s = arabic.letters(quote_word), arabic.letters(source_word)
    if len(q) != len(s):
        return "significant"
    for a, b in zip(q, s):
        if a != b and (a, b) not in _BENIGN:
            return "significant"
    return "benign"


def compare_words(quote_words: list[str], source_words: list[str]) -> dict:
    """Classify an exact folded match as literal / diacritics / normalized / uthmani.

    ``uthmani``: some words are a recognised Uthmani spelling of the source word (``uthmani.explain``); the words
    themselves are listed in ``uthmani_words`` and a vowel the quote writes differently in ``diacritic_conflicts``.
    """
    script_diffs, diac_conflicts, uth_words = [], [], []
    all_literal = True
    for qw, sw in zip(quote_words, source_words):
        if arabic.literal(qw) == arabic.literal(sw):
            continue
        all_literal = False
        features = uthmani.explain(qw, sw) if uthmani.features(qw) else None
        if features is not None:
            uth_words.append({"quote": qw, "source": sw, "features": list(features)})
            vowels = uthmani.vowel_conflicts(qw, sw)
            if vowels:
                diac_conflicts.append({"quote": qw, "source": sw, "uthmani": True, "marks": [m for _, m in vowels]})
        elif arabic.letters(qw) != arabic.letters(sw):
            script_diffs.append({"quote": qw, "source": sw, "kind": script_diff_kind(qw, sw)})
        elif arabic.has_diacritics(qw) and diacritics_conflict(qw, sw):
            diac_conflicts.append({"quote": qw, "source": sw})
    if all_literal:
        level = "literal"
    elif uth_words:
        level = "uthmani"
    elif script_diffs:
        level = "normalized"
    else:
        level = "diacritics"
    vocalized = any(arabic.has_diacritics(w) for w in quote_words)
    return {"level": level, "script_diffs": script_diffs, "diacritic_conflicts": diac_conflicts, "uthmani_words": uth_words,
            "quote_vocalized": vocalized}


SCRIPT_LABEL = "الرسم العثماني"
SCRIPT_MESSAGE = "الألفاظ ألفاظ المصحف نفسها مكتوبةً بالرسم العثماني، وقد طابقناها مع نص قرآنبيديا بعد توحيد الرسم. لا يلزم تصحيح."


def script_block(uth_words: list[dict]) -> dict | None:
    """Which script convention the matched words are written in, and for which words (None if none needed it)."""
    if not uth_words:
        return None
    features = sorted({f for w in uth_words for f in w["features"]})
    return {"convention": "uthmani", "label": SCRIPT_LABEL, "features": features, "words": uth_words[:12], "word_count": len(uth_words)}


# ---------------------------------------------------------------------------
# fuzzy alignment
# ---------------------------------------------------------------------------

@dataclass
class Alignment:
    span: Span
    similarity: float
    ops: list[tuple[str, int, int, int, int]]  # difflib opcodes relative to span


def _align(index: QuranIndex, qf: list[str], surah: int, w0: int, w1: int, extend: bool = True) -> Alignment | None:
    stream = index.streams[surah]
    w0, w1 = max(0, w0), min(len(stream), w1)
    window = [stream[p][0] for p in range(w0, w1)]
    sm = SequenceMatcher(None, qf, window, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size]
    if not blocks:
        return None
    first, last = blocks[0], blocks[-1]
    j0, j1 = first.b, last.b + last.size
    if extend:  # include words substituted at the edges of the quotation
        j0 = max(0, j0 - first.a)
        j1 = min(len(window), j1 + (len(qf) - (last.a + last.size)))
    sub = window[j0:j1]
    sm2 = SequenceMatcher(None, qf, sub, autojunk=False)
    matched = sum(b.size for b in sm2.get_matching_blocks())
    sim = 2 * matched / (len(qf) + len(sub)) if sub else 0.0
    return Alignment(Span(surah, w0 + j0, w0 + j1), sim, sm2.get_opcodes())


def fuzzy_candidates(index: QuranIndex, qf: list[str], extra: list[Span] | None = None, limit: int = 3) -> list[Alignment]:
    """Closest passages by diagonal voting on rare shared words + alignment."""
    n = len(qf)
    total = max(1, len(index.ayahs))
    votes: dict[tuple[int, int], float] = defaultdict(float)
    for i, w in enumerate(qf):
        df = index.doc_freq.get(w)
        if not df:
            continue
        weight = math.log(total / df) + 0.1
        for s, p in index.positions.get(w, []):
            votes[(s, p - i)] += weight
    # smooth neighbouring diagonals (insertions/deletions shift the diagonal)
    smoothed: dict[tuple[int, int], float] = {}
    for (s, d), v in votes.items():
        smoothed[(s, d)] = v + sum(votes.get((s, d + k), 0.0) for k in (-2, -1, 1, 2))
    top = sorted(smoothed.items(), key=lambda kv: -kv[1])
    seen: set[tuple[int, int]] = set()
    results: list[Alignment] = []
    for (s, d), _ in top:
        if len(seen) >= 8:
            break
        key = (s, d // 4)
        if key in seen:
            continue
        seen.add(key)
        al = _align(index, qf, s, d - 4, d + n + 4)
        if al:
            results.append(al)
    for sp in extra or []:
        al = _align(index, qf, sp.surah, sp.p0, sp.p1)
        if al:
            results.append(al)
    # dedupe by span, keep best
    best: dict[tuple[int, int, int], Alignment] = {}
    for al in results:
        k = (al.span.surah, al.span.p0, al.span.p1)
        if k not in best or best[k].similarity < al.similarity:
            best[k] = al
    # Whole-word similarity ties often (one word differs in each place); then the place whose differing word is spelt like the
    # writer's comes first: «كل نفس بما كسبت رهين» is المدثر 38 («رهينة»), not الرعد 33, whose next word is «وجعلوا».
    return sorted(best.values(), key=lambda a: (-a.similarity, -_near_pairs(index, qf, a)))[:limit]


NEAR_RATIO = 0.75  # letter similarity of a misspelt or inflected word (the phrase search's SOFT_RATIO)


def _near_pairs(index: QuranIndex, qf: list[str], al: Alignment) -> int:
    """Substituted words of an alignment that are near in spelling to the source word they replace."""
    stream = index.streams[al.span.surah]
    words = [stream[p][0] for p in range(al.span.p0, al.span.p1)]
    n = 0
    for tag, i1, i2, j1, j2 in al.ops:
        if tag == "replace":
            n += sum(1 for a, b in zip(qf[i1:i2], words[j1:j2])
                     if len(a) >= 3 and len(b) >= 3 and SequenceMatcher(None, a, b, autojunk=False).ratio() >= NEAR_RATIO)
    return n


def diff_ops(quote_words: list[str], source_words: list[str], opcodes) -> list[dict]:
    """Human-readable word diff: equal / replace / extra (only in quote) / missing (only in source)."""
    out = []
    for tag, i1, i2, j1, j2 in opcodes:
        q = " ".join(quote_words[i1:i2])
        s = " ".join(source_words[j1:j2])
        kind = {"equal": "equal", "replace": "replace", "delete": "extra", "insert": "missing"}[tag]
        out.append({"op": kind, "quote": q, "source": s})
    return out


def script_unresolved(quote_words: list[str], source_words: list[str], ops) -> tuple[dict[int, str], bool]:
    """Quote words the fuzzy alignment pairs with a source word of the same consonants although the word shows an Uthmani
    feature: the spelling may be a correct one that no rule covers. ``{quote index: source word}`` and whether *every*
    difference of the alignment is of this kind (then nothing is known to be wrong)."""
    found: dict[int, str] = {}
    other = False
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            continue
        pairs = [(i1 + k, quote_words[i1 + k], source_words[j1 + k]) for k in range(i2 - i1)] if tag == "replace" and i2 - i1 == j2 - j1 else []
        flagged = [(k, qw, sw) for k, qw, sw in pairs if uthmani.features(qw) and uthmani.same_skeleton(qw, sw)]
        for k, _, sw in flagged:
            found[k] = sw
        if not pairs or len(flagged) != len(pairs):
            other = True
    return found, bool(found) and not other


# ---------------------------------------------------------------------------
# reference checking
# ---------------------------------------------------------------------------

def ref_overlaps(ref: Reference, index: QuranIndex, span: Span) -> tuple[bool, bool]:
    """(overlaps, fully_covers) for a valid reference against a located span."""
    if ref.surah != span.surah:
        return False, False
    if ref.ayah_start is None:
        return True, True
    a0, a1 = span_ayahs(index, span)
    r0, r1 = ref.ayah_start, ref.ayah_end or ref.ayah_start
    overlaps = r0 <= a1 and a0 <= r1
    return overlaps, overlaps and r0 <= a0 and a1 <= r1


def ref_span(index: QuranIndex, ref: Reference) -> Span | None:
    if not ref.valid:
        return None
    if ref.ayah_start is None:
        return None
    a1 = ref.ayah_end or ref.ayah_start
    try:
        p0 = index.ayah_pos[(ref.surah, ref.ayah_start)][0]
        p1 = index.ayah_pos[(ref.surah, a1)][1]
    except KeyError:
        return None
    return Span(ref.surah, p0, p1)


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

def _source_block(index: QuranIndex, span: Span) -> dict:
    a0, a1 = span_ayahs(index, span)
    segs = span_segments(index, span)
    return {
        "surah": span.surah,
        "surah_name": NAMES.get(span.surah),
        "ayah_start": a0,
        "ayah_end": a1,
        "label": span_label(index, span),
        "coverage": coverage(index, span),
        "matched_text": " ".join(span_words(index, span)),
        "segments": [
            {
                "ayah": s["ayah"],
                "words": s["words"],
                "from": s["from"],
                "to": s["to"],
                "api_url": ayah_api_url(span.surah, s["ayah"]),
                "page_url": ayah_page_url(span.surah, s["ayah"]),
            }
            for s in segs
        ],
    }


def unavailable_result(ref: Reference | None) -> dict:
    """Result when Quranpedia could not be reached: nothing is verified."""
    reasons = ["تعذّر الوصول إلى مصدر النص القرآني (قرآنبيديا)، فلم يُتحقق من النص."]
    ref_block = {"status": "missing" if ref is None else "uncertain", "found": ref.to_dict() if ref else None, "expected": None, "message": ""}
    if ref is None:
        ref_block["message"] = "لم تُذكر إحالة بجوار الاقتباس."
    elif not ref.valid:
        ref_block["status"] = "incorrect"
        ref_block["message"] = "؛ ".join(ref.problems)
    else:
        ref_block["message"] = "الإحالة سليمة الصيغة، لكن تعذّر التحقق من مطابقتها للنص لغياب المصدر."
    return {
        "wording": {"status": "uncertain", "level": None, "similarity": None, "message": "المصدر غير متاح", "diff": [], "script_diffs": [], "diacritic_conflicts": [], "script": None},
        "proposal": {"status": "review_only", "edits": [], "vocalize": [], "script": [], "reason": "المصدر غير متاح؛ لا يُقترح أي تصحيح."},
        "source": None,
        "alternatives": [],
        "occurrences": None,
        "reference": ref_block,
        "needs_review": True,
        "review_reasons": reasons,
    }


def verify(index: QuranIndex, quote_words: list[str], ref: Reference | None,
           pin: Reference | None = None, hints: list[Span] | None = None, bounded: bool = False) -> dict:
    """Verify a quotation given as a list of raw article words.

    ``pin`` is a verse the editor chose by hand. It settles the location the way a nearby written reference
    does (repeated or very short phrases), but is never reported as a reference the writer wrote.
    ``hints`` are places the phrase search thinks are close; they are only *offered* to the fuzzy alignment,
    they never make a match count as a reference and they confirm nothing.
    ``bounded`` is True when a marker (brackets, quotation marks) or the editor's own selection states where the quotation
    begins and ends; only then may a one-word substitution in a very short quotation be corrected (see ``propose_wording``).
    """
    qf = [arabic.search_fold(w) for w in quote_words]
    quote_alts = [uthmani.alternatives(w) for w in quote_words]
    reasons: list[str] = []
    wording: dict = {"status": "uncertain", "level": None, "similarity": None, "message": "", "diff": [], "script_diffs": [], "diacritic_conflicts": [], "script": None}
    chosen: Span | None = None
    alternatives: list[dict] = []
    occurrences = 0
    fuzzy = False

    fuzzy_best: Alignment | None = None
    fuzzy_good: list[Alignment] = []
    exact = find_exact(index, qf, quote_alts)
    occurrences = len(exact)
    ref_ok = ref if (ref and ref.valid) else None
    loc = ref_ok or (pin if (pin and pin.valid) else None)  # what settles the location: a written reference, else the chosen verse

    if exact:
        confirmed = [sp for sp in exact if loc and ref_overlaps(loc, index, sp)[0]]
        if len(exact) == 1 and len(qf) >= MIN_WORDS:
            chosen = exact[0]
        elif confirmed and (len(confirmed) == 1 or loc.ayah_start is not None):
            chosen = confirmed[0]
            if len(exact) > 1:
                by = "وحددت الإحالةُ المجاورة موضعها" if loc is ref_ok else "وحدّدتَ الموضع بنفسك"
                wording["message"] = f"العبارة واردة في {len(exact)} مواضع، {by}."
        elif len(exact) == 1:
            chosen = exact[0]
            reasons.append(f"الاقتباس قصير ({len(qf)} كلمة)، ولا يكفي وحده لتأكيد أنه اقتباس قرآني.")
        else:
            reasons.append(f"العبارة واردة في {len(exact)} مواضع من القرآن؛ يلزم تحديد الموضع المقصود.")
            alternatives = [{"label": span_label(index, sp), "similarity": 1.0, "source": _source_block(index, sp)} for sp in exact[:MAX_LISTED]]

        if chosen is not None:
            cmp = compare_words(quote_words, span_words(index, chosen))
            wording.update({"level": cmp["level"], "similarity": 1.0, "script_diffs": cmp["script_diffs"], "diacritic_conflicts": cmp["diacritic_conflicts"],
                            "script": script_block(cmp["uthmani_words"])})
            significant = [d for d in cmp["script_diffs"] if d["kind"] == "significant"]
            if significant or cmp["diacritic_conflicts"]:
                wording["status"] = "difference"
                if cmp["uthmani_words"] and not significant:
                    msg = "الكلمات مطابقة بعد توحيد الرسم العثماني، لكن تشكيل بعضها يخالف نص المصحف؛ يُراجَع يدويًا ولا يُستبدل تلقائيًا (قد يرجع إلى اختلاف طبعات المصاحف في الضبط)."
                else:
                    what = "في رسم بعض الحروف (كالهمزات)" if significant else "في التشكيل"
                    msg = f"الكلمات مطابقة بعد التطبيع، لكن {what} اختلاف عن نص المصحف."
                    if not significant:
                        msg += " قد يرجع بعضه إلى اختلاف طريقة الضبط بين طبعات المصاحف (كعلامات الإدغام)، فيُرجى التأكد."
                wording["message"] = (wording["message"] + " " if wording["message"] else "") + msg
            else:
                short_unconfirmed = len(qf) < MIN_WORDS and not (loc and ref_overlaps(loc, index, chosen)[0])
                wording["status"] = "uncertain" if short_unconfirmed else "matched"
                if wording["status"] == "matched" and cmp["level"] == "uthmani":
                    wording["message"] = (wording["message"] + " " if wording["message"] else "") + SCRIPT_MESSAGE
            wording["diff"] = [{"op": "equal", "quote": " ".join(quote_words), "source": " ".join(span_words(index, chosen))}]
        else:
            wording["status"] = "uncertain"
    else:
        extra = [sp for sp in [ref_span(index, loc)] if sp] if loc else []
        extra += [h for h in (hints or []) if h.surah in index.streams]
        cands = fuzzy_candidates(index, qf, extra) if len(qf) >= MIN_WORDS or extra else []
        good = [c for c in cands if c.similarity >= FUZZY_ACCEPT and sum(i2 - i1 for t, i1, i2, _, _ in c.ops if t == "equal") >= 2]
        if good:
            best = good[0]
            # prefer the referenced passage when it is (nearly) as close as the best one
            for c in good:
                if loc and ref_overlaps(loc, index, c.span)[0] and c.similarity >= best.similarity - 0.05:
                    best = c
                    break
            chosen = best.span
            fuzzy = True
            fuzzy_best, fuzzy_good = best, good
            wording.update({
                "status": "difference",
                "level": "fuzzy",
                "similarity": round(best.similarity, 3),
                "message": "لم يُعثر على النص بحروفه في المصدر؛ هذا أقرب موضع مقترح وليس تحققًا.",
                "diff": diff_ops(quote_words, span_words(index, chosen), best.ops),
            })
            reasons.append("مطابقة تقريبية: الموضع المقترح يحتاج إلى تأكيد بشري.")
            unresolved, only_script = script_unresolved(quote_words, span_words(index, chosen), best.ops)
            if unresolved:
                wording["unresolved_words"] = [{"quote": quote_words[k], "source": w} for k, w in sorted(unresolved.items())]
                names = "، ".join(quote_words[k] for k in sorted(unresolved))
                if only_script:
                    # Every other word equals the source: the only open question is a spelling no rule covers.
                    wording.update(status="uncertain", message=f"باقي الكلمات مطابقة للمصحف، لكن رسم «{names}» لم نستطع مطابقته آليًا بالرسم العثماني؛ يلزم التحقق يدويًا ولا يُقترح تصحيح.")
                    fuzzy = False
                    reasons[:] = [r for r in reasons if not r.startswith("مطابقة تقريبية")]
                    reasons.append(wording["message"])
                else:
                    reasons.append(f"رسم «{names}» لم نستطع مطابقته آليًا بالرسم العثماني، فلا يُستبدل تلقائيًا.")
            alternatives = [
                {"label": span_label(index, c.span), "similarity": round(c.similarity, 3), "source": _source_block(index, c.span)}
                for c in good if c is not best
            ][: MAX_LISTED - 1]
        else:
            wording["message"] = "لم يُعثر على نص مطابق أو قريب بدرجة كافية في المصدر."
            reasons.append("لم يُعثر على الاقتباس في النص القرآني؛ قد لا يكون آية أو قد يكون منقولًا بتصرف كبير.")

    reference = check_reference(index, ref, chosen, fuzzy, exact)
    if reference["status"] in ("incorrect", "uncertain"):
        reasons.append(reference["message"])
    if wording["status"] == "uncertain" and not reasons:
        reasons.append(wording["message"] or "حالة غير محسومة.")
    needs_review = wording["status"] != "matched" or reference["status"] in ("incorrect", "uncertain") or fuzzy
    if wording["status"] == "difference" and not fuzzy:
        # deterministic letter-form / diacritics finding; still worth a human look
        reasons.append(wording["message"])

    proposal = propose_wording(index, quote_words, wording, chosen, fuzzy_best, fuzzy_good, loc, bounded)
    return {
        "wording": wording,
        "proposal": proposal,
        "source": _source_block(index, chosen) if chosen else None,
        "alternatives": alternatives,
        "occurrences": occurrences,
        "reference": reference,
        "needs_review": bool(needs_review),
        "review_reasons": list(dict.fromkeys(r for r in reasons if r)),
    }


# ---------------------------------------------------------------------------
# correction proposals (deterministic; replacement words come ONLY from the source)
# ---------------------------------------------------------------------------

FUZZY_PROPOSE_WITH_REF = 0.75  # min similarity when the nearby reference confirms the location
FUZZY_PROPOSE_NO_REF = 0.8  # min similarity when there is no reference at all
FUZZY_MARGIN = 0.1  # the runner-up location must be at least this much less similar


def styled(source_word: str, like_quote_word: str | None, quote_vocalized: bool) -> str:
    """Source word in the article's writing style: vocalized only if the article vocalized it.

    Quranic pause/annotation marks are always dropped (they are not wording).
    """
    vocal = arabic.has_diacritics(like_quote_word) if like_quote_word is not None else quote_vocalized
    return arabic.literal(source_word) if vocal else arabic.letters(source_word)


def _word_fixes(quote_words: list[str], source_words: list[str], q0: int, s0: int, n: int, vocalized: bool) -> list[tuple[int, int, list[str]]]:
    """One-to-one fixes for words that fold equal: significant letter-form changes and diacritic conflicts."""
    edits = []
    for k in range(n):
        qw, sw = quote_words[q0 + k], source_words[s0 + k]
        if uthmani.features(qw) and uthmani.explain(qw, sw) is not None:
            continue  # a recognised Uthmani spelling: never a wording error (a vowel conflict is for the editor to review)
        if arabic.letters(qw) != arabic.letters(sw):
            if script_diff_kind(qw, sw) == "significant":
                edits.append((q0 + k, q0 + k + 1, [styled(sw, qw, vocalized)]))
        elif arabic.has_diacritics(qw) and diacritics_conflict(qw, sw):
            edits.append((q0 + k, q0 + k + 1, [arabic.literal(sw)]))
    return edits


def _one_word_swapped(best: Alignment) -> bool:
    """The quotation differs from its closest passage by exactly one word written in place of another one.

    Word-level similarity cannot rate such a quotation above (n-1)/n, which is 0.667 for three words, so the
    similarity floors below could never be met by a three-word quotation however well everything else is confirmed.
    """
    others = [op for op in best.ops if op[0] != "equal"]
    equal = sum(i2 - i1 for tag, i1, i2, _, _ in best.ops if tag == "equal")
    return equal >= 2 and len(others) == 1 and others[0][0] == "replace" and others[0][2] - others[0][1] == 1 and others[0][4] - others[0][3] == 1


def _one_word_swapped_and_one_missing(best: Alignment) -> bool:
    """A pinned, bounded quotation may have one wrong word and one omitted word.

    Keep the waiver narrow: three words must still match in order, the replacement is
    one-for-one, and exactly one source word is missing. A verse number and the
    separate rival check are required by ``propose_wording`` before this is used.
    """
    others = [op for op in best.ops if op[0] != "equal"]
    equal = sum(i2 - i1 for tag, i1, i2, _, _ in best.ops if tag == "equal")
    return (equal >= 3 and len(others) == 2
            and any(t == "replace" and i2 - i1 == j2 - j1 == 1 for t, i1, i2, j1, j2 in others)
            and any(t == "insert" and i1 == i2 and j2 - j1 == 1 for t, i1, i2, j1, j2 in others))


def propose_wording(index: QuranIndex, quote_words: list[str], wording: dict, chosen: Span | None,
                    best: Alignment | None, good: list[Alignment], ref_ok: Reference | None, bounded: bool = False) -> dict:
    """Decide whether a source-backed wording correction can be offered.

    Returns ``{"status": ..., "edits": [...], "vocalize": [...], "reason": str}``:
      * ``none_needed`` — the wording matches (a canonical vocalization may still be offered
        as an explicit, optional editor choice in ``vocalize``);
      * ``proposed``    — ``edits`` (quote-token ranges → source words) fix the wording;
      * ``review_only`` — the intended source span is not certain; no replacement is offered.
    Edits never extend beyond the quoted excerpt, so a partial quote is never expanded to a full verse.
    """
    out = {"status": "review_only", "edits": [], "vocalize": [], "script": [], "reason": ""}
    vocalized = any(arabic.has_diacritics(w) for w in quote_words)
    if chosen is None:
        out["reason"] = "موضع الاقتباس في المصحف غير محدد (غير موجود أو وارد في أكثر من موضع)، فلا يُقترح تصحيح تلقائي."
        return out
    src = span_words(index, chosen)
    if best is None:  # exact folded match at a single, confirmed location
        if wording["status"] == "uncertain":
            out["reason"] = "الاقتباس قصير ولم تؤكد إحالةٌ موضعَه، فلا يُقترح تصحيح تلقائي."
            return out
        edits = _word_fixes(quote_words, src, 0, 0, len(quote_words), vocalized)
        if edits:
            out.update(status="proposed", edits=edits, reason=wording.get("message") or "")
            return out
        if any(d.get("uthmani") for d in wording.get("diacritic_conflicts", [])):
            out["reason"] = "تشكيل بعض الكلمات يخالف نص المصحف (والرسم عثماني)؛ يُراجَع يدويًا ولا يُستبدل تلقائيًا."
            return out
        out["status"] = "none_needed"
        if wording.get("level") != "literal":
            differing = [(k, qw, sw) for k, (qw, sw) in enumerate(zip(quote_words, src)) if arabic.literal(qw) != arabic.literal(sw)]
            as_script = {k for k, qw, sw in differing if uthmani.features(qw) and uthmani.explain(qw, sw) is not None}
            # Optional formatting, never a correction: the Uthmani spelling is right; these write it the way Quranpedia does.
            # (one conversion for the whole quotation when any word needs it, else the plain full-vocalisation option)
            key = "script" if as_script else "vocalize"
            out[key] = [(k, k + 1, [arabic.literal(sw)]) for k, qw, sw in differing]
        return out
    # fuzzy: only when the location is unambiguous and supported
    if len(quote_words) < MIN_WORDS:
        out["reason"] = "الاقتباس أقصر من أن يُحدَّد موضعه بالمطابقة التقريبية."
        return out
    rivals = [c for c in good if c is not best and not ref_overlaps_span(c.span, best.span)]
    close_rival = bool(rivals) and max(c.similarity for c in rivals) >= best.similarity - FUZZY_MARGIN
    if ref_ok is not None and ref_ok.ayah_start is not None and close_rival:
        # a reference with an ayah number may disambiguate, but only if no close rival is also in it
        if any(ref_overlaps(ref_ok, index, c.span)[0] for c in rivals if c.similarity >= best.similarity - FUZZY_MARGIN):
            out["reason"] = "أكثر من موضع قريب يقع ضمن الإحالة المكتوبة؛ اختر الموضع المقصود يدويًا."
            return out
    elif close_rival:
        out["reason"] = "يوجد أكثر من موضع قريب في المصحف ولا تحدده إحالة برقم الآية؛ اختر الموضع المقصود يدويًا."
        return out
    if ref_ok is not None:
        if not ref_overlaps(ref_ok, index, best.span)[0]:
            out["reason"] = "الإحالة المكتوبة لا تشير إلى أقرب موضع، فلا يُعرف الموضع المقصود يقينًا."
            return out
        # A three-word quotation with one word changed scores 0.667, under the floor, whatever else is settled. When the
        # writer's marker or selection states its boundaries, an ayah-level reference (or chosen verse) points at the
        # closest passage (checked above), no close rival exists and nothing but that one word differs, the floor is waived.
        waived = bounded and ref_ok.ayah_start is not None and (
            _one_word_swapped(best) or _one_word_swapped_and_one_missing(best))
        if best.similarity < FUZZY_PROPOSE_WITH_REF and not waived:
            out["reason"] = "الفرق كبير بين الاقتباس وأقرب موضع؛ يلزم تحقق بشري."
            return out
    elif best.similarity < FUZZY_PROPOSE_NO_REF:
        out["reason"] = "لا توجد إحالة تؤكد الموضع، والتشابه غير كافٍ لاقتراح تصحيح تلقائي."
        return out
    unresolved, only_script = script_unresolved(quote_words, src, best.ops)
    if only_script:
        out["reason"] = "باقي الكلمات مطابقة، لكن رسم كلمة لم نستطع مطابقته آليًا بالرسم العثماني؛ لا يُقترح استبدال."
        return out
    edits: list[tuple[int, int, list[str]]] = []
    for tag, i1, i2, j1, j2 in best.ops:
        if tag == "equal":
            edits += _word_fixes(quote_words, src, i1, j1, i2 - i1, vocalized)
        elif tag == "replace" and unresolved and i2 - i1 == j2 - j1:
            for k in range(i2 - i1):  # one word for one word: the words whose spelling may be correct are left alone
                if i1 + k not in unresolved:
                    edits.append((i1 + k, i1 + k + 1, [styled(src[j1 + k], quote_words[i1 + k], vocalized)]))
        elif tag == "replace":
            ql = quote_words[i1:i2]
            edits.append((i1, i2, [styled(src[j], ql[j - j1] if j - j1 < len(ql) else None, vocalized) for j in range(j1, j2)]))
        elif tag == "delete":
            edits.append((i1, i2, []))
        else:  # insert: words missing from the quote
            edits.append((i1, i1, [styled(src[j], None, vocalized) for j in range(j1, j2)]))
    if not edits:
        out["reason"] = "تعذّر بناء تصحيح آمن."
        return out
    if not bounded and any(not words and (i1 == 0 or i2 == len(quote_words)) for i1, i2, words in edits):
        # A span whose edges the program chose, not the writer: a word to delete at its first or last place is more likely
        # the writer's own prose next to the quotation than an extra word inside it. Nothing is offered; the writer settles it.
        out["reason"] = "حدود الاقتباس غير محسومة: الكلمة الزائدة في طرفه قد تكون من كلامك لا من الاقتباس، فلا يُقترح حذفها."
        return out
    out.update(status="proposed", edits=edits, reason="الاقتباس يختلف عن نص المصحف في الموضع المحدد؛ التصحيح المقترح مأخوذ من قرآنبيديا لهذا المقطع فقط.")
    return out


def ref_overlaps_span(a: Span, b: Span) -> bool:
    return a.surah == b.surah and a.p0 < b.p1 and b.p0 < a.p1


def check_reference(index: QuranIndex, ref: Reference | None, chosen: Span | None, fuzzy: bool, exact: list[Span]) -> dict:
    expected = span_label(index, chosen) if chosen else None
    block = {"status": "uncertain", "found": ref.to_dict() if ref else None, "expected": expected, "message": ""}
    if ref is None:
        block["status"] = "missing"
        block["message"] = "لم تُذكر إحالة (سورة/آية) بجوار الاقتباس." + (f" الموضع: {expected}." if expected and not fuzzy else "")
        return block
    if not ref.valid:
        block["status"] = "incorrect"
        block["message"] = "إحالة غير صالحة: " + "؛ ".join(ref.problems)
        return block
    if chosen is None:
        if exact and ref.ayah_start is not None and not any(ref_overlaps(ref, index, sp)[0] for sp in exact):
            block["status"] = "incorrect"
            places = "، ".join(span_label(index, sp) for sp in exact[:MAX_LISTED])
            block["message"] = f"العبارة غير موجودة في الموضع المحال إليه ({ref.label()})؛ وردت في: {places}."
        else:
            block["message"] = "تعذّر التحقق من الإحالة لأن موضع الاقتباس لم يُحدَّد."
        return block
    overlaps, covers = ref_overlaps(ref, index, chosen)
    if fuzzy:
        if overlaps:
            block["message"] = f"الإحالة ({ref.label()}) تشير إلى الموضع الأقرب، لكن النص نفسه مختلف؛ يلزم التأكد."
        else:
            block["message"] = f"الإحالة ({ref.label()}) لا تشير إلى الموضع الأقرب المقترح ({expected})؛ يلزم التأكد."
        return block
    if overlaps and covers:
        block["status"] = "matched"
        block["message"] = "الإحالة مطابقة لموضع الاقتباس." if ref.ayah_start else f"ذُكرت السورة دون رقم الآية؛ الموضع: {expected}."
    elif overlaps:
        block["status"] = "uncertain"
        block["message"] = f"الإحالة ({ref.label()}) لا تغطي كل الآيات المقتبسة؛ الموضع الكامل: {expected}."
    else:
        block["status"] = "incorrect"
        block["message"] = f"الإحالة ({ref.label()}) لا تطابق موضع النص؛ الموضع في المصدر: {expected}."
    return block
