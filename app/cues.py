"""Quotations the writer announced: retrieval anchored on the writer's own cues (no model).

The unmarked-phrase search (``phrases.py``) must keep ordinary Arabic from looking like a verse, so it ignores short,
common or loosely matching phrases. A writer often says where a verse is, though, without brackets:

* a lead-in such as «قال تعالى:» or «يقول الله عز وجل» right before the words;
* a written reference with a surah (and usually an ayah) right after the words («… [طه: 114]»), or right before them
  («في سورة الرعد، الآية 11: …»);
* quotation marks «…» / "…" / “…” around them (with no lead-in or reference; those are already "marked").

Inside such an announced window the evidence that a verse is meant comes from the writer, so the retrieval may accept a
weaker lexical match than the phrase search does: two or three matched words, one or two of them changed or missing. The
retrieval looks only where the cue points: the referenced verse (and its neighbours), the referenced surah, or the whole
text for a lead-in or quotation marks. What it returns is a *place to look*:

* the window's words are aligned to source words; the span shown is the hull of the aligned words, widened by one
  unmatched word only at an edge the writer's cue states (the word right after a lead-in, the word right before the
  reference, the first and last word inside quotation marks);
* the audit verifies the span against the source like any other candidate and grades it: an exact match goes through the
  ordinary tier rules, anything approximate is only "possible" and offers no replacement text until the writer confirms the
  quotation and the verse (``audit._detection``).

Nothing here changes text, and every word shown or proposed later comes from the source through the verifier.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from . import arabic
from .phrases import ANCHOR_IDF, _QURAN, _fold_phrase, _segments, _soft
from .quran_source import QuranIndex
from .references import Reference
from .verifier import Span

MAX_WINDOW = 40            # words looked at after a lead-in / before a reference / inside quotation marks
MIN_SIMILARITY = 0.6       # 2·matched / (span words + verse words) over the aligned hull
NEIGHBOUR_AYAHS = 1        # a reference may be off by one ayah; the neighbours are searched too
SEED_DF_MAX = 1500         # words that vote for a place (rarer than this many ayahs)

# Extra wording of lead-ins (folded) beyond the list the tiers use (``phrases._QURAN_CUES``).
_EXTRA_LEAD_INS = [
    "قال عز وجل", "يقول عز وجل", "قوله عز وجل", "قال جل وعلا", "يقول جل وعلا", "في كتاب الله", "في التنزيل",
    "في محكم التنزيل", "في الذكر الحكيم", "الله يقول", "ربنا يقول", "قال الحق", "يقول الحق", "قال جل شأنه",
    "قوله", "بقوله", "وقوله",   # «… بقوله وما يعقلها إلا العالمون»: the classical way of citing a verse
]
# Words of praise that may follow a lead-in before the verse begins («يقول الله عز وجل: …», «في كتابه العزيز: …»).
_HONORIFICS = {arabic.folded(w) for w in ("عز", "وجل", "جل", "وعلا", "سبحانه", "وتعالى", "تعالى", "تبارك", "جلاله", "شأنه",
                                          "العزيز", "الكريم", "الحكيم", "المبين", "المجيد")}
# Nouns that name the Quran or a verse («القرآن», «الآية») announce the words that follow only when a colon introduces them
# («ورد في القرآن الكريم: …»); in running prose they are a topic («حذّر القرآن من الذين …»), not a lead-in.
_NOUN_CUES = {_fold_phrase(c) for c in ("في القرآن", "القرآن الكريم", "القرآن", "الآية", "آية", "في كتابه")}
_LEAD_INS = sorted(set(_QURAN) | {_fold_phrase(c) for c in _EXTRA_LEAD_INS}, key=len, reverse=True)
_LAST_WORDS = {c[-1] for c in _LEAD_INS if c}
_QUOTE_PAIRS = {"«": "»", '"': '"', "“": "”", "”": "“"}


@dataclass
class Cue:
    kind: str                       # "lead_in" | "reference" | "quotes"
    first: int                      # window: article token range [first, last)
    last: int
    states_start: bool              # the cue says where the quotation begins / ends
    states_end: bool
    ref: Reference | None = None


@dataclass
class CueHit:
    first: int                      # token range of the proposed span [first, last)
    last: int
    cue: Cue
    span: Span                      # the aligned source words
    matched: int
    exact: int
    similarity: float
    mass: float
    edge_words: list[str] = field(default_factory=list)   # "start"/"end": an unmatched word kept because the cue states that edge
    window: tuple[int, int] = (0, 0)                      # the announced window as character offsets (set by the audit)


def _ends_with(words: tuple[str, ...], end: int, nouns: bool = True) -> int:
    """Length of the lead-in that ends at token index ``end`` (exclusive), 0 if none (``nouns``: count «القرآن», «الآية» …)."""
    for c in _LEAD_INS:
        n = len(c)
        if n <= end and words[end - n:end] == c and (nouns or c not in _NOUN_CUES):
            return n
    return 0


def announced_before(before: str) -> bool:
    """True if ``before`` ends with a lead-in such as «قال تعالى» or «يقول الله عز وجل» (a verse is announced right here).

    The same lead-ins as ``phrases.ends_with_quran_cue`` plus a few more wordings, with words of praise after them allowed.
    """
    words = _fold_phrase(before)
    j = len(words)
    while j > 0 and words[j - 1] in _HONORIFICS and not _ends_with(words, j):
        j -= 1
    return bool(_ends_with(words, j))


def find_cues(article: str, tokens: list[arabic.Token], refs: list[Reference]) -> list[Cue]:
    """Windows the writer announced as a verse (a lead-in and a reference around the same words make one window)."""
    folds = tuple(t.fold for t in tokens)
    seg_of: dict[int, tuple[int, int]] = {}
    for lo, hi in _segments(article, tokens):
        for k in range(lo, hi):
            seg_of[k] = (lo, hi)
    starts = [t.start for t in tokens]
    ends = [t.end for t in tokens]
    lead: list[Cue] = []
    after_ref: list[Cue] = []
    other: list[Cue] = []

    # 1) lead-ins: «قال تعالى: …», «يقول الله عز وجل …»
    for k in range(1, len(tokens)):
        if k not in seg_of or (folds[k - 1] not in _LAST_WORDS and folds[k - 1] not in _HONORIFICS):
            continue
        j = k
        while j > 0 and folds[j - 1] in _HONORIFICS and not _ends_with(folds, j):
            j -= 1
        g = article[tokens[k - 1].end:tokens[k].start]
        if not _ends_with(folds, j, nouns=":" in g):
            continue
        if "\n" in g or g.strip(" \t\u00a0:،,-–—") != "":
            continue  # a bracket or quotation mark opens here: the marker states the quotation (marked extraction)
        if folds[k] in _HONORIFICS and not g.strip(" \t\u00a0"):
            continue  # «يقول الله عز وجل …»: the words of praise still belong to the lead-in; the window starts after them
        _, hi = seg_of[k]
        lead.append(Cue("lead_in", k, min(hi, k + MAX_WINDOW), True, False))
    # 2) references right after the words (… [طه: 114]) or right before them (… الآية 11: …)
    for r in refs:
        if not r.valid:
            continue
        i = bisect_right(ends, r.start) - 1
        if i >= 0 and i in seg_of:
            g = article[tokens[i].end:r.start]
            # a citation closes the quotation: in brackets or after a dash, or the compact «طه: 114» form; «… في سورة العنكبوت»
            # in running prose names the surah of what comes next instead
            cited = any(ch in g for ch in "([{-–—") or (r.ayah_start is not None and ":" in r.text)
            if "\n" not in g and g.strip(" \t\u00a0([{-–—،,") == "" and cited:
                lo, _ = seg_of[i]
                after_ref.append(Cue("reference", max(lo, i + 1 - MAX_WINDOW), i + 1, False, True, r))
        i = bisect_left(starts, r.end)
        if i < len(tokens) and i in seg_of:
            g = article[r.end:tokens[i].start].strip(" \t\u00a0)]}")
            if "\n" not in g and g in (":", "،:", ":،", "-", "—", "،"):
                _, hi = seg_of[i]
                other.append(Cue("reference", i, min(hi, i + MAX_WINDOW), True, False, r))
    # a lead-in and a reference around the same words: the lead-in states the start, the reference the end and the verse
    merged: list[Cue] = []
    used = set()
    for c in lead:
        partner = next((n for n, a in enumerate(after_ref) if n not in used and a.last == c.last), None)
        if partner is not None:
            used.add(partner)
            merged.append(Cue("reference", c.first, c.last, True, True, after_ref[partner].ref))
        else:
            merged.append(c)
    merged += [a for n, a in enumerate(after_ref) if n not in used]
    # 3) quotation marks around the words
    k = 0
    while k < len(article):
        close = _QUOTE_PAIRS.get(article[k])
        if close is None:
            k += 1
            continue
        e = article.find(close, k + 1)
        if e < 0 or "\n" in article[k:e] or e - k > 1500:
            k += 1
            continue
        a, b = bisect_left(starts, k + 1), bisect_right(ends, e)
        if 2 <= b - a <= MAX_WINDOW:
            other.append(Cue("quotes", a, b, True, True))
        k = e + 1
    return merged + other


class _Retriever:
    def __init__(self, index: QuranIndex):
        self.index = index
        self.total = max(1, index.ayah_count)

    def idf(self, w: str) -> float:
        df = self.index.doc_freq.get(w)
        return math.log(self.total / df) if df else math.log(self.total)

    def regions(self, wf: list[str], cue: Cue) -> list[tuple[int, int, int]]:
        """Places of the source to align with: (surah, p0, p1) stream ranges."""
        idx = self.index
        r = cue.ref
        if r is not None and r.ayah_start is not None:
            a0 = max(1, r.ayah_start - NEIGHBOUR_AYAHS)
            a1 = (r.ayah_end or r.ayah_start) + NEIGHBOUR_AYAHS
            while a1 > a0 and (r.surah, a1) not in idx.ayah_pos:
                a1 -= 1
            if (r.surah, a0) not in idx.ayah_pos:
                return []
            return [(r.surah, idx.ayah_pos[(r.surah, a0)][0], idx.ayah_pos[(r.surah, a1)][1])]
        surahs = {r.surah} if r is not None else None
        votes: dict[tuple[int, int], float] = defaultdict(float)
        for i, w in enumerate(wf):
            df = idx.doc_freq.get(w)
            if not df or df > SEED_DF_MAX:
                continue
            weight = self.idf(w)
            for s, p in idx.positions.get(w, []):
                if surahs is None or s in surahs:
                    votes[(s, p - i)] += weight
        smoothed = {(s, d): v + sum(votes.get((s, d + k), 0.0) for k in (-2, -1, 1, 2)) for (s, d), v in votes.items()}
        out, seen = [], set()
        n = len(wf)
        for (s, d), _ in sorted(smoothed.items(), key=lambda kv: -kv[1]):
            if len(out) >= 6:
                break
            if (s, d // 4) in seen:
                continue
            seen.add((s, d // 4))
            out.append((s, max(0, d - 4), min(len(idx.streams[s]), d + n + 4)))
        return out

    def align(self, wf: list[str], s: int, p0: int, p1: int) -> list[tuple[int, int, str]]:
        """Monotone word alignment of the window with stream[p0:p1]: (window index, stream position, "E"|"S")."""
        region = [self.index.streams[s][p][0] for p in range(p0, p1)]
        rset = set(region)
        mapped, kinds = [], []
        for w in wf:
            if w in rset:
                mapped.append(w)
                kinds.append("E")
                continue
            near = [x for x in rset if _soft(w, x)]
            if near:
                best = max(near, key=lambda x: SequenceMatcher(None, w, x, autojunk=False).ratio())
                mapped.append(best)
                kinds.append("S")
            else:
                mapped.append("\x00" + w)
                kinds.append(None)
        sm = SequenceMatcher(None, mapped, region, autojunk=False)
        pairs = []
        for b in sm.get_matching_blocks():
            for k in range(b.size):
                pairs.append((b.a + k, p0 + b.b + k, kinds[b.a + k]))
        return pairs

    def best(self, tokens: list[arabic.Token], cue: Cue) -> CueHit | None:
        wf = [t.fold for t in tokens[cue.first:cue.last]]
        if len(wf) < 2:
            return None
        stream_of = self.index.streams
        best: CueHit | None = None
        for s, p0, p1 in self.regions(wf, cue):
            pairs = self.align(wf, s, p0, p1)
            if not pairs:
                continue
            pairs = _densest_run(pairs, lambda p, s=s: self.idf(stream_of[s][p][0]))
            h0, h1 = pairs[0][0], pairs[-1][0] + 1
            q0, q1 = pairs[0][1], pairs[-1][1] + 1
            matched = len(pairs)
            exact = sum(1 for p in pairs if p[2] == "E")
            mass = sum(self.idf(stream_of[s][p][0]) * (1.0 if k == "E" else 0.5) for _, p, k in pairs)
            edges: list[str] = []
            # one unmatched edge word is kept only where the writer's cue states that edge and the verse has a word there
            if cue.states_start and h0 == 1 and q0 - 1 >= 0 and stream_of[s][q0 - 1][1] == stream_of[s][q0][1]:
                h0, q0 = 0, q0 - 1
                edges.append("start")
            if cue.states_end and h1 == len(wf) - 1 and q1 < len(stream_of[s]) and stream_of[s][q1][1] == stream_of[s][q1 - 1][1]:
                h1, q1 = len(wf), q1 + 1
                edges.append("end")
            sim = 2 * matched / ((h1 - h0) + (q1 - q0))
            hit = CueHit(cue.first + h0, cue.first + h1, cue, Span(s, q0, q1), matched, exact, sim, mass, edges)
            if best is None or (hit.matched, hit.similarity, hit.mass) > (best.matched, best.similarity, best.mass):
                best = hit
        return best if best is not None and _accept(best, len(wf)) else None


def _densest_run(pairs: list[tuple[int, int, str]], idf) -> list[tuple[int, int, str]]:
    """The main run of the alignment, without stray matches.

    Gaps of more than 3 words on either side end a run, and the longest run is kept. Inside it, as in the phrase search
    (``phrases._Searcher._supported``), whatever lies beyond a gap must be backed by two consecutive matched words or by one
    exact word that is rare in the Quran: one loosely matching word of prose after a comma is not absorbed into the quotation.
    """
    runs: list[list[tuple[int, int, str]]] = [[pairs[0]]]
    for a, b in zip(pairs, pairs[1:]):
        if b[0] - a[0] > 3 or b[1] - a[1] > 3:
            runs.append([b])
        else:
            runs[-1].append(b)
    run = max(runs, key=len)
    blocks: list[list[tuple[int, int, str]]] = [[run[0]]]
    for a, b in zip(run, run[1:]):
        if b[0] - a[0] > 1 or b[1] - a[1] > 1:
            blocks.append([b])
        else:
            blocks[-1].append(b)

    def weak(block) -> bool:
        return len(block) < 2 and not (block[0][2] == "E" and idf(block[0][1]) >= ANCHOR_IDF)

    while len(blocks) > 1 and weak(blocks[0]):
        blocks.pop(0)
    while len(blocks) > 1 and weak(blocks[-1]):
        blocks.pop()
    return [p for b in blocks for p in b]


def _accept(h: CueHit, window: int) -> bool:
    """Is the aligned passage close enough to say "this may be the verse the writer announced"?"""
    if h.similarity < MIN_SIMILARITY or h.exact < 2:
        return False
    c, r = h.cue, h.cue.ref
    # the cue announces the words right next to it: the match must start (or end) there, give or take the one word
    # that may be the wrong word at that edge
    if c.states_start and h.first - c.first > 1:
        return False
    if c.states_end and c.last - h.last > 1:
        return False
    words = h.last - h.first
    if c.kind == "reference" and r is not None and r.ayah_start is not None:
        # the writer named the verse: two exact words of that verse (or its neighbours) next to the reference suffice
        return h.matched >= 2 and (h.matched >= 3 or words <= 3)
    if c.kind == "reference":  # surah named, no ayah
        return h.matched >= 3 and h.mass >= 8.0
    if c.kind == "lead_in":
        return h.matched >= 3 and h.mass >= 12.0
    # quotation marks with no lead-in or reference: the weakest cue, so the strictest bar, and most of the quote must align
    return h.matched >= 3 and h.mass >= 12.0 and words >= 0.6 * window


def find_cue_hits(article: str, tokens: list[arabic.Token], refs: list[Reference], index: QuranIndex) -> list[CueHit]:
    """One best source passage per announced window, if any is close enough (see the module docstring)."""
    r = _Retriever(index)
    hits: list[CueHit] = []
    found = [h for cue in find_cues(article, tokens, refs) if (h := r.best(tokens, cue)) is not None]
    # the strongest announcement first: a named verse, then a lead-in, then a named surah, then quotation marks
    rank = lambda h: (0 if h.cue.ref is not None and h.cue.ref.ayah_start is not None else 1 if h.cue.kind == "lead_in" else  # noqa: E731
                      2 if h.cue.kind == "reference" else 3, -h.matched, h.first)
    for h in sorted(found, key=rank):
        if not any(h.first < x.last and x.first < h.last for x in hits):
            hits.append(h)
    return sorted(hits, key=lambda h: h.first)
