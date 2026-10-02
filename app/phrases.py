"""Search ordinary article text for short Quran phrases that carry no brackets, quotation marks or reference.

Memory: nothing is indexed per phrase. The search reuses the word index that already exists
(``QuranIndex.positions`` = folded word → places, ``QuranIndex.streams`` = the folded words of each
surah in order). It is *seed and extend*: every article word that is rare in the Quran is a seed; for
each place where it occurs, the match is extended to the left and right along that surah's word
stream. Normalization (``arabic.folded``) is used for searching only; the text shown, compared and
copied always comes from the source via the verifier.

Detection and verification are separate. This module only decides *where* a Quran phrase may be and
*how sure it is that the writer meant a quotation* (``tier``); ``verifier.verify`` then compares the
words with the source and proposes nothing on its own.

tier
    candidate  an exact (folded) match of a distinctive phrase: at least 4 words of words that are rare in
               the Quran (or 5+ words), not a formula, not introduced as a hadith/du'a/proverb.
    possible   everything else that is reported: a short or common exact phrase, a formula introduced by a
               Quran cue, a phrase after a hadith/du'a/proverb cue, or an approximate match (one or two
               words differ).

Phrases too short or too common to be told apart from ordinary Arabic, and bare everyday formulae, are not
reported; they are counted (``PhraseScan.suppressed``) so the interface can say so and offer manual selection.

The search cannot know where a writer's quotation ends: a wrong first or last word looks like ordinary prose
next to the quotation, so it is not absorbed (the audit shows the verse's next word beside the article's).

How the parameters below were chosen, and what was and was not held out, is written up in docs/EVALUATION.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache

from . import arabic
from .quran_source import QuranIndex
from .verifier import Span, script_diff_kind, source_word

# --- parameters (chosen on the main/held-out sets, a synthetic benchmark and ordinary-prose samples; the frozen
#     phrase set was run afterwards, and docs/EVALUATION.md discloses the two bug fixes made after its first run)
SEED_DF_MAX = 300          # a seed word occurs in at most this many ayahs (rarer words start a search)
MIN_EXACT_WORDS = 3        # shortest exact phrase that is reported at all
MASS_FLOOR = 12.0          # exact phrases below this rarity mass are too common to report
MASS_CANDIDATE = 20.0      # ... and from this mass up (with >= 4 words) they are candidates
MASS_APPROX = 16.0         # minimum mass of the matched words of an approximate phrase
APPROX_MIN_WORDS = 4       # ... and the fewest matched words (exact or near) in one
SOFT_RATIO = 0.75          # letter similarity at which two different words count as a near match
ANCHOR_IDF = 5.0           # a lone exact word beyond an edit counts as support only if it is this rare (idf)
MAX_EDITS = 2              # whole-word substitutions / insertions / omissions inside one approximate phrase
MAX_SEED_STEPS = 80_000    # work budget per article (seed occurrences visited); real articles need <= ~41,000, repeated frequent words would need far more
MAX_SPANS = 60             # Quran places kept for one phrase

# Phrases used as everyday formulae (folded words). They ARE Quran text, but a writer who uses one is rarely
# quoting a verse: they are hidden, unless a Quran cue ("قال تعالى") precedes them, and then never "candidate".
_FORMULAS = [
    "بسم الله الرحمن الرحيم", "الحمد لله رب العالمين", "لا إله إلا الله", "إنا لله وإنا إليه راجعون",
    "إن شاء الله", "ما شاء الله", "سبحان الله", "والله أعلم", "والله أعلم بالصواب", "لا حول ولا قوة إلا بالله",
    "لا قوة إلا بالله", "صدق الله العظيم", "والله على كل شيء قدير", "إن الله على كل شيء قدير",
    "والله غفور رحيم", "وعلى الله فليتوكل المتوكلون", "حسبنا الله ونعم الوكيل", "ونعم الوكيل",
    "أعوذ بالله من الشيطان الرجيم", "بالله من الشيطان الرجيم", "رب العالمين", "أستغفر الله", "جزاك الله خيرا",
    "إن الله غفور رحيم", "والله بكل شيء عليم", "والله سميع عليم", "يوم القيامة",
    "رضي الله عنهم", "رضي الله عنه", "رضي الله عنها", "لا شريك له", "محمد رسول الله", "سبحانه وتعالى", "تبارك وتعالى",
    "عز وجل", "جل جلاله", "لا إله إلا أنت", "من الشيطان الرجيم",
]

# A hadith/du'a/proverb/maxim introduced just before the phrase makes a Quran quotation less likely.
_NON_QURAN_CUES = [
    "قال رسول الله", "قال النبي", "قال الرسول", "صلى الله عليه وسلم", "الحديث", "حديث", "الحديث الشريف", "روى", "رواه",
    "اللهم", "دعاء", "الدعاء", "الأدعية", "يدعو", "المثل", "الأمثال", "يقال", "قالت العرب", "حكمة", "الحكمة",
    "القاعدة", "القواعد", "الفقهية", "قال الشاعر", "قال الإمام", "قال بعض", "قال ابن", "قال أبو",
]
_QURAN_CUES = [
    "قال تعالى", "قوله تعالى", "يقول تعالى", "وقال تعالى", "والله يقول", "قال الله", "يقول الله", "يقول ربنا", "قال ربنا",
    "قوله سبحانه", "قال سبحانه", "في كتابه", "في القرآن", "القرآن الكريم", "القرآن", "الآية", "آية",
]
_ALLOWED_GAP = " \t ،,؛;ۖۗۘۙۚۛۜ"  # Quranic pause signs (ۖ ۗ ۚ ...) between the words of a copied verse do not end a phrase


def _fold_phrase(text: str) -> tuple[str, ...]:
    return tuple(t.fold for t in arabic.tokenize(text))


_FORMULA_SET = [_fold_phrase(f) for f in _FORMULAS]
_NON_QURAN = [_fold_phrase(c) for c in _NON_QURAN_CUES]
_QURAN = [_fold_phrase(c) for c in _QURAN_CUES]


@dataclass
class PhraseHit:
    first: int                      # article token range [first, last)
    last: int
    exact: bool                     # every word folds equal to the Quran (no near-match word, no edit)
    spans: list[Span]               # where it occurs (all places if exact, the best alignment if approximate)
    mass: float                     # rarity mass of the matched Quran words (sum of ln(ayahs / ayahs containing the word))
    matched: int                    # words matched (exact + near)
    soft: int = 0                   # near-match words (differ in a letter or two)
    edits: int = 0                  # substituted / inserted / omitted whole words
    tier: str = "possible"
    reasons: list[str] = field(default_factory=list)   # codes: common, approximate, formula, non_quran_cue

    @property
    def words(self) -> int:
        return self.last - self.first


@dataclass
class PhraseScan:
    hits: list[PhraseHit]
    suppressed: list[PhraseHit] = field(default_factory=list)  # exact phrases too short/common to report (manual selection still works)
    steps: int = 0
    truncated: bool = False         # the work budget ran out; the rest of the article was not searched


def _overlap(a: str, b: str) -> int:
    return sum(min(a.count(ch), b.count(ch)) for ch in set(a))


@lru_cache(maxsize=20000)
def _soft(a: str, b: str) -> bool:
    """Two different folded words that are probably the same word misspelt or inflected."""
    if len(a) < 3 or len(b) < 3 or abs(len(a) - len(b)) > 3 or _overlap(a, b) < min(len(a), len(b)) - 1:
        return False  # cheap rejection before the costly ratio
    return SequenceMatcher(None, a, b, autojunk=False).ratio() >= SOFT_RATIO


def _segments(article: str, tokens: list[arabic.Token]) -> list[tuple[int, int]]:
    """Runs of tokens separated only by whitespace (and commas); any other character ends a run."""
    n = len(tokens)
    bad = [False] * n  # expanded ligatures (e.g. ﷺ → several tokens with one span) cannot be edited word by word
    for k in range(1, n):
        if (tokens[k].start, tokens[k].end) == (tokens[k - 1].start, tokens[k - 1].end):
            bad[k] = bad[k - 1] = True
    segs: list[tuple[int, int]] = []
    a = 0
    for k in range(1, n + 1):
        brk = k == n or bad[k] or bad[k - 1]
        if not brk:
            gap = article[tokens[k - 1].end:tokens[k].start]
            brk = "\n" in gap or gap.strip(_ALLOWED_GAP) != ""
        if brk:
            if not bad[a]:
                segs.append((a, k))
            a = k
    return segs


class _Searcher:
    def __init__(self, article: str, tokens: list[arabic.Token], index: QuranIndex):
        self.article, self.tokens, self.index = article, tokens, index
        self.af = [t.fold for t in tokens]
        self.total = max(1, index.ayah_count)
        self._idf: dict[str, float] = {}
        self.steps = 0

    def idf(self, w: str) -> float:
        v = self._idf.get(w)
        if v is None:
            df = self.index.doc_freq.get(w)
            v = math.log(self.total / df) if df else math.log(self.total)
            self._idf[w] = v
        return v

    # -- alignment around one seed ------------------------------------------------------------
    def _match(self, a: str, w: str) -> str | None:
        if a == w:
            return "E"
        return "S" if _soft(a, w) else None

    def _extend(self, lo: int, hi: int, stream, i: int, p: int, step: int, budget: int):
        """Walk from the matched pair (i, p) in one direction; return ([(tok, pos, kind)], edits)."""
        af, n = self.af, len(stream)
        pairs: list[tuple[int, int, str]] = []
        edits = 0
        ci, cp = i + step, p + step

        def ok(x: int, y: int) -> bool:
            return lo <= x < hi and 0 <= y < n

        while ok(ci, cp):
            a, w = af[ci], stream[cp][0]
            kind = self._match(a, w)
            if kind:
                pairs.append((ci, cp, kind))
                ci += step
                cp += step
                continue
            if edits >= budget:
                break
            ni, nc = ci + step, cp + step
            if ok(ni, nc) and self._match(af[ni], stream[nc][0]):      # one word replaced
                ci, cp = ni, nc
            elif ok(ni, cp) and self._match(af[ni], w):                # one extra word in the article
                ci = ni
            elif ok(ci, nc) and self._match(a, stream[nc][0]):         # one word of the verse left out
                cp = nc
            elif edits + 2 <= budget and ok(ci, cp + 2 * step) and self._match(a, stream[cp + 2 * step][0]):  # two left out
                cp += 2 * step
                edits += 1
            else:
                break
            edits += 1
        return pairs, edits

    def _trim(self, pairs: list[tuple[int, int, str]], s: int) -> list[tuple[int, int, str]]:
        """Drop edge words that would absorb ordinary prose: near-match edges of a weak hit, and
        exact-by-folding words whose letters differ significantly (e.g. إن written for أن)."""
        exact_words = sum(1 for x in pairs if x[2] == "E")

        def bad_edge(pr: tuple[int, int, str]) -> bool:
            ti, sp, kind = pr
            if kind == "S":
                return exact_words < 3
            src = source_word(self.index, s, sp)
            return arabic.letters(self.tokens[ti].raw) != arabic.letters(src) and script_diff_kind(self.tokens[ti].raw, src) not in ("benign", "uthmani")

        pairs = list(pairs)
        while pairs and bad_edge(pairs[0]):
            exact_words -= pairs.pop(0)[2] == "E"
        while pairs and bad_edge(pairs[-1]):
            exact_words -= pairs.pop()[2] == "E"
        return pairs

    def _supported(self, pairs: list[tuple[int, int, str]], s: int) -> list[tuple[int, int, str]]:
        """Whatever lies beyond an edit (a replaced / extra / omitted word) must be backed by two matched
        words, or by one exact word that is rare in the Quran; one near-match word is too weak to justify
        stretching a phrase over a neighbouring word of ordinary prose."""
        if not pairs:
            return pairs
        stream = self.index.streams[s]
        blocks: list[list[tuple[int, int, str]]] = [[pairs[0]]]
        for a, b in zip(pairs, pairs[1:]):
            if b[0] - a[0] > 1 or b[1] - a[1] > 1:
                blocks.append([b])
            else:
                blocks[-1].append(b)

        def weak(block: list[tuple[int, int, str]]) -> bool:
            if len(block) >= 2:
                return False
            ti, sp, kind = block[0]
            return not (kind == "E" and self.idf(stream[sp][0]) >= ANCHOR_IDF)

        while len(blocks) > 1 and weak(blocks[0]):
            blocks.pop(0)
        while len(blocks) > 1 and weak(blocks[-1]):
            blocks.pop()
        return [p for b in blocks for p in b]

    def alignments(self) -> tuple[list[dict], bool]:
        """Every seed-and-extend alignment found (before thresholds decide which are reported)."""
        index, af = self.index, self.af
        done: set[tuple[int, int, int]] = set()
        raw: list[dict] = []
        truncated = False
        for lo, hi in _segments(self.article, self.tokens):
            for i in range(lo, hi):
                w = af[i]
                df = index.doc_freq.get(w)
                if not df or df > SEED_DF_MAX:
                    continue
                for s, p in index.positions[w]:
                    self.steps += 1
                    if (s, i, p) in done:
                        continue
                    stream = index.streams[s]
                    left, e_left = self._extend(lo, hi, stream, i, p, -1, MAX_EDITS)
                    right, _ = self._extend(lo, hi, stream, i, p, +1, MAX_EDITS - e_left)
                    if len(left) + len(right) < 2:  # a hit needs three matched words
                        continue
                    pairs = list(reversed(left)) + [(i, p, "E")] + right
                    for _ in range(3):  # trimming and support checks can expose each other's edges
                        before = len(pairs)
                        pairs = self._trim(self._supported(pairs, s), s)
                        if len(pairs) == before:
                            break
                    for ti, sp, _ in pairs:
                        done.add((s, ti, sp))
                    if not pairs:
                        continue
                    e = sum(1 for x in pairs if x[2] == "E")
                    sft = sum(1 for x in pairs if x[2] == "S")
                    first, last = pairs[0][0], pairs[-1][0] + 1
                    # edits = words that sit between two matched pairs on one side only or on both (a replaced word counts once)
                    edits = sum(max(b[0] - a[0] - 1, b[1] - a[1] - 1) for a, b in zip(pairs, pairs[1:]))
                    mass = sum(self.idf(stream[sp][0]) * (1.0 if kind == "E" else 0.5) for _, sp, kind in pairs)
                    raw.append({"first": first, "last": last, "s": s, "p0": pairs[0][1], "p1": pairs[-1][1] + 1,
                                "E": e, "S": sft, "X": edits, "mass": mass, "n": len(pairs)})
                if self.steps > MAX_SEED_STEPS:
                    truncated = True
                    break
            if truncated:
                break
        return raw, truncated

    def run(self) -> tuple[list[PhraseHit], bool]:
        raw, truncated = self.alignments()
        return self._resolve(raw), truncated

    # -- from raw alignments to reportable hits -------------------------------------------------
    def _resolve(self, raw: list[dict]) -> list[PhraseHit]:
        exact: dict[tuple[int, int], list[dict]] = {}
        approx: list[dict] = []
        for r in raw:
            if r["S"] == 0 and r["X"] == 0:
                if r["E"] >= MIN_EXACT_WORDS:
                    exact.setdefault((r["first"], r["last"]), []).append(r)
            elif r["E"] >= 2 and r["n"] >= APPROX_MIN_WORDS and r["X"] <= MAX_EDITS and r["X"] <= r["n"] // 2 and r["mass"] >= MASS_APPROX:
                approx.append(r)
        hits: list[PhraseHit] = []
        for (first, last), rs in exact.items():
            spans = [Span(r["s"], r["p0"], r["p1"]) for r in rs][:MAX_SPANS]
            hits.append(PhraseHit(first, last, True, spans, rs[0]["mass"], rs[0]["n"]))
        for r in approx:
            hits.append(PhraseHit(r["first"], r["last"], False, [Span(r["s"], r["p0"], r["p1"])], r["mass"], r["n"], r["S"], r["X"]))
        # the strongest evidence first; a weaker hit that overlaps an accepted one is dropped
        hits.sort(key=lambda h: (-h.mass, h.first))
        kept: list[PhraseHit] = []
        for h in hits:
            if any(h.first < k.last and k.first < h.last for k in kept):
                continue
            kept.append(h)
        return sorted(kept, key=lambda h: h.first)

    # -- tiers ------------------------------------------------------------------------------------
    def classify(self, h: PhraseHit) -> bool:
        """Set the tier and reasons; False if the hit is too common to report."""
        cue = quran_cue(self.article, self.tokens[h.first].start)
        if h.exact:
            graded = grade_exact(tuple(self.af[h.first:h.last]), h.mass, cue)
            if graded is None:
                return False
            h.tier, h.reasons = graded
        else:
            h.tier, h.reasons = grade_approximate(cue)
        return True


def quran_cue(article: str, start: int) -> str | None:
    """"quran" if the sentence so far says a verse follows, "non_quran" if it says a hadith/du'a/proverb does."""
    window = article[max(0, start - 70):start]
    cut = max(window.rfind(ch) for ch in ".!؟?\n")
    words = _fold_phrase(window[cut + 1:] if cut >= 0 else window)
    if any(_contains(words, c) for c in _QURAN):
        return "quran"
    return "non_quran" if any(_contains(words, c) for c in _NON_QURAN) else None


def grade_exact(words: tuple[str, ...], mass: float, cue: str | None) -> tuple[str, list[str]] | None:
    """Tier and reasons of an exact (folded) Quran phrase, or None if it is too common to report.

    One rule for every unmarked span, whoever proposed it: the phrase search grades the hits it finds with it,
    and the audit grades a span that only the AI proposed with the same function.
    """
    if mass < MASS_FLOOR:
        return None
    reasons: list[str] = []
    if any(_contains(words, f) for f in _FORMULA_SET):
        if cue != "quran":
            return None  # an everyday formula with nothing saying "this is a verse": not reported
        reasons.append("formula")
    if cue == "non_quran":
        reasons.append("non_quran_cue")
    if not (len(words) >= 4 and mass >= MASS_CANDIDATE) and not (len(words) >= 5 and mass >= MASS_FLOOR + 4):
        reasons.append("common")
    return ("candidate" if not reasons else "possible"), reasons


def grade_approximate(cue: str | None) -> tuple[str, list[str]]:
    """An unmarked phrase whose words differ from the text is never more than "possible"."""
    return "possible", ["approximate"] + (["non_quran_cue"] if cue == "non_quran" else [])


def span_mass(index: QuranIndex, words: tuple[str, ...]) -> float:
    """Rarity mass of folded words: sum of ln(ayahs / ayahs containing the word), as in ``_Searcher.idf``."""
    total = max(1, index.ayah_count)
    return sum(math.log(total / index.doc_freq[w]) if index.doc_freq.get(w) else math.log(total) for w in words)


def _contains(words: tuple[str, ...], sub: tuple[str, ...]) -> bool:
    n = len(sub)
    return n > 0 and any(words[i:i + n] == sub for i in range(len(words) - n + 1))


def ends_with_quran_cue(before: str) -> bool:
    """True if the text just before a span ends with a lead-in such as «قال تعالى» (a verse is announced right here)."""
    words = _fold_phrase(before)
    return any(len(c) <= len(words) and words[len(words) - len(c):] == c for c in _QURAN)


def find_phrases(article: str, tokens: list[arabic.Token], index: QuranIndex) -> PhraseScan:
    """Reportable Quran phrases in ``article`` (see the module docstring for the tiers)."""
    s = _Searcher(article, tokens, index)
    hits, truncated = s.run()
    kept: list[PhraseHit] = []
    suppressed: list[PhraseHit] = []
    for h in hits:
        (kept if s.classify(h) else suppressed).append(h)
    return PhraseScan(kept, suppressed, s.steps, truncated)
