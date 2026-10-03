"""Source-backed verse suggestions while the writer types (no AI, no network call per request).

Every proposed word and reference comes from the Quranpedia Hafs text already loaded in ``QuranIndex``
(``Ayah.words``). Nothing here is generated, and no language model takes part: the text typed before the caret is
looked up in the word index that the audit already uses, so a suggestion is exactly as trustworthy as the source.

What is suggested
    continue       the typed words are the start of a verse (a distinctive exact prefix): the next few words, an exact
                   continuation. A short chunk (at most ``CHUNK_WORDS`` words, or the rest of the verse when only a few
                   remain) is offered, never the whole verse unasked; ``extend_text`` carries the remainder.
    complete_word  the caret sits inside the last word and it is a proper prefix of the verse's next word.
    replace        the typed words are a distinctive exact prefix, but the last typed word (followed by a space) is not
                   the verse's next word: a *probable* correction, never applied unasked.
    insert         the last typed word equals the verse word after one or two others: those words are missing.

When it speaks (conservative on purpose)
    * an explicit Quran lead-in directly before the typed words («قال تعالى»), or a quotation / verse bracket that is
      still open (﴿ « " “ {), or a Quran lead-in earlier in the same sentence, or the writer asked («أكمل من المصحف»);
    * with ``distinct`` on, also a long, rare exact prefix with no cue at all;
    * never after a hadith / du'a / proverb cue (unless the writer opened a verse bracket or asked), never for an
      everyday formula without a cue, never for words that match very many places.

Ambiguity is returned as several places (``ambiguous``), never as one arbitrary confident choice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import arabic
from .phrases import (MASS_CANDIDATE, _ALLOWED_GAP, _FORMULA_SET, _contains, ends_with_quran_cue, quran_cue, span_mass)
from .quran_source import QuranIndex, ayah_page_url
from .surahs import NAMES
from .verifier import styled

MAX_BEFORE = 800        # characters of context the endpoint reads before the caret
MAX_AFTER = 120
MAX_RUN_WORDS = 40      # longest typed run compared with the text
CHUNK_WORDS = 4         # words offered at once from the middle of a verse
CHUNK_TAIL = 5          # ... or the rest of the verse when this few remain
MAX_CHOICES = 4
MAX_PLACES = {2: 6, 3: 12}   # how many places a match of this length may have before it is called too common (>=4 words: 16)
DEFAULT_MAX_PLACES = 16
MIN_WORDS = {"cue": 2, "opener": 2, "explicit": 2, "cue_sentence": 3, "distinct": 4}
MIN_MASS = {2: 7.0, 3: 9.0}  # rarity mass of the matched words (sum of ln(ayahs/ayahs containing the word))
DEFAULT_MIN_MASS = 9.0
CORRECTION_MIN_WORDS = 3     # typed words that must match before a different last word is called a probable error
CORRECTION_MIN_MASS = 12.0
CORRECTION_MAX_PLACES = 2
SKIP_MAX = 2                 # a typed word equal to the verse word this far ahead means words were left out
ANCHOR_DOMINATES = 2         # a longer exact beginning that ends one word earlier beats a short match of the whole run elsewhere by this many words
MID_WORD_MIN_LETTERS = 4     # a word still being typed is called a probable error only from this many letters (explicit: any)
MAX_OPENER_GAP = 1           # words allowed between an opening mark and the matched words (a stray lead-in word such as a wrong first word)

_OPEN_QUOTES = "﴿«“{"
_CLOSERS_FOR = {"﴿": "﴾", "«": "»", "“": "”", "{": "}", "(": ")", "[": "]"}
_SENTENCE_END = ".!؟?\n"
_PAUSE_SIGNS = "ۖۗۘۙۚۛۜ"

ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


@dataclass
class _Place:
    surah: int
    pos: int      # stream position of the last matched typed word
    length: int   # typed words matched, ending at ``pos``


def _eq(tok: arabic.Token, folded_word: str) -> bool:
    return folded_word == tok.fold or folded_word in tok.alts


def _trailing_run(before: str, tokens: list[arabic.Token]) -> tuple[list[arabic.Token], str] | None:
    """The tokens of the writer's current run (separated only by spaces / commas) and the text after the last one."""
    if not tokens:
        return None
    tail = before[tokens[-1].end:]
    if any(ch not in _ALLOWED_GAP for ch in tail):
        return None  # a full stop, a closing bracket, a newline or other text follows the last word: nothing to continue
    first = len(tokens) - 1
    while first > 0:
        gap = before[tokens[first - 1].end:tokens[first].start]
        if "\n" in gap or gap.strip(_ALLOWED_GAP) != "" or (tokens[first - 1].start, tokens[first - 1].end) == (tokens[first].start, tokens[first].end):
            break
        first -= 1
    return tokens[max(first, len(tokens) - MAX_RUN_WORDS):], tail


def _open_quote(text: str) -> int | None:
    """Offset of the innermost quotation / verse bracket still open at the end of ``text`` (None if there is none)."""
    stack: list[tuple[str, int]] = []
    for i, ch in enumerate(text):
        if ch in _OPEN_QUOTES or ch in "([":
            stack.append((ch, i))
        elif ch == '"':
            if stack and stack[-1][0] == '"':
                stack.pop()
            else:
                stack.append(('"', i))
        elif ch in "﴾»”})]":
            for j in range(len(stack) - 1, -1, -1):
                if _CLOSERS_FOR.get(stack[j][0]) == ch:
                    del stack[j:]
                    break
    quotes = [s for s in stack if s[0] in _OPEN_QUOTES or s[0] == '"']
    return quotes[-1][1] if quotes else None


def _trigger(before: str, run: list[arabic.Token], k: int, explicit: bool, distinct: bool) -> tuple[str | None, str | None]:
    """(trigger, blocked_reason) for matched words starting at ``run[k]``."""
    start = run[k].start
    ahead = before[:start]
    cue = quran_cue(before, start)
    open_at = _open_quote(before)
    if open_at is not None and open_at < start:
        between = arabic.tokenize(before[open_at:start])
        if len(between) <= MAX_OPENER_GAP and not any(ch in _SENTENCE_END for ch in before[open_at:start]):
            return "opener", None
    if ends_with_quran_cue(ahead[-80:]) and not any(ch in _SENTENCE_END for ch in ahead[-3:]):
        return "cue", None
    if explicit:
        return "explicit", None   # the writer asked: the lowest bar (two words), whatever else the sentence mentions
    if cue == "quran":
        return "cue_sentence", None
    if cue == "non_quran":
        return None, "non_quran_cue"
    if distinct:
        return "distinct", None
    return None, "no_trigger"


def _places(index: QuranIndex, run: list[arabic.Token], end: int) -> list[_Place]:
    """Every place where the typed words ``run[:end]`` end, with how many of them (counted backwards) match there."""
    if end <= 0:
        return []
    last = run[end - 1]
    out: list[_Place] = []
    seen: set[tuple[int, int]] = set()
    for f in (last.fold, *last.alts):
        for s, p in index.positions.get(f, ()):
            if (s, p) in seen:
                continue
            seen.add((s, p))
            stream = index.streams[s]
            n = 1
            while n < end and p - n >= 0 and _eq(run[end - 1 - n], stream[p - n][0]):
                n += 1
            out.append(_Place(s, p, n))
    return out


def _label(surah: int, a0: int, a1: int) -> str:
    name = NAMES.get(surah, str(surah))
    return f"{name}: {a0}" if a0 == a1 else f"{name}: {a0}–{a1}"


def _verse_block(index: QuranIndex, surah: int, ayah_no: int, typed: tuple[int, int], added: tuple[int, int]) -> dict:
    a = index.ayahs[(surah, ayah_no)]
    return {"text": a.text, "words": a.words, "typed": list(typed), "added": list(added), "page_url": ayah_page_url(surah, ayah_no)}


def _chunk_bounds(n_words: int, nxt: int) -> tuple[int, int]:
    """Word range [nxt, end) offered from a verse of ``n_words`` words whose next unwritten word is ``nxt``."""
    remaining = n_words - nxt
    take = remaining if remaining <= CHUNK_TAIL else CHUNK_WORDS
    return nxt, nxt + take


class _Style:
    def __init__(self, run: list[arabic.Token]):
        self.vocal = any(arabic.has_diacritics(t.raw) for t in run[-4:])

    def words(self, ws: list[str]) -> str:
        return " ".join(styled(w, None, self.vocal) for w in ws)


def _choice_from(index: QuranIndex, surah: int, ayah_no: int, nxt: int, typed_end: int, pl: _Place, style: _Style, lead: str,
                 typed_n: int, kind: str, replace: tuple[int, int], from_text: str, certainty: str, words_override: list[str] | None = None) -> dict | None:
    """One choice that proposes the words of ``ayah_no`` from word ``nxt`` on (a short chunk)."""
    a = index.ayahs[(surah, ayah_no)]
    if nxt >= len(a.words):
        return None
    lo, hi = _chunk_bounds(len(a.words), nxt)
    chunk = a.words[lo:hi]
    rest = a.words[hi:]
    first_ayah = index.streams[surah][pl.pos - pl.length + 1][1] if pl.length > 0 else ayah_no
    to_text = style.words(chunk)
    return {
        "kind": kind,
        "certainty": certainty,
        "replace_start": replace[0],
        "replace_end": replace[1],
        "from_text": from_text,
        "to_text": to_text,
        "insert_text": lead + to_text,
        "extend_text": (" " + style.words(rest)) if rest else None,
        "typed_words": typed_n,
        "added_words": len(chunk),
        "remaining_words": len(rest),
        "surah": surah,
        "surah_name": NAMES.get(surah, str(surah)),
        "ayah_start": first_ayah,
        "ayah_end": ayah_no,
        "label": _label(surah, first_ayah, ayah_no),
        "verse": _verse_block(index, surah, ayah_no, (max(0, nxt - typed_n), typed_end), (lo, hi)),
    }


def suggest(index: QuranIndex, before: str, after: str = "", *, explicit: bool = False, distinct: bool = False) -> dict:
    """Suggestions for the caret placed at the end of ``before`` (code-point offsets in the result refer to ``before``)."""
    before = before[-MAX_BEFORE:]   # the endpoint already refuses more; offsets in the result refer to this (untruncated) string
    after = after[:MAX_AFTER]
    base = {"status": "none", "reason": None, "trigger": None, "choices": [], "ambiguous": False, "places": 0}

    def none(reason: str, **extra) -> dict:
        return {**base, "reason": reason, **extra}

    tokens = arabic.tokenize(before)
    got = _trailing_run(before, tokens)
    if got is None:
        return {**base, "status": "hint", "reason": "too_short"} if explicit else none("no_trigger")
    run, tail = got
    mid_word = tail == ""
    # Caret inside an existing word (text continues without a space): never interrupt an edit in the middle of a word.
    if mid_word and after and arabic.is_arabic_letter(after[0]):
        return none("inside_word")
    n = len(run)
    after_tokens = arabic.tokenize(after)
    after_fold = after_tokens[0].fold if after_tokens and not after[:after_tokens[0].start].strip(_ALLOWED_GAP) else None

    # 1) the typed words themselves (the last one is complete, or is a word being typed)
    full = _places(index, run, n)
    best_full = max((p.length for p in full), default=0)
    # 2) the typed words without the last one (the last may be wrong, or still being typed)
    anchor_places = _places(index, run, n - 1) if n >= 2 else []
    best_anchor = max((p.length for p in anchor_places), default=0)

    results: list[dict] = []
    trigger: str | None = None
    blocked: str | None = None
    total_places = 0

    def gate(places: list[_Place], length: int, words_start: int, need_mass: bool = True) -> tuple[str | None, str | None]:
        """Trigger for matched words run[words_start:words_start+length] and whether they are distinctive enough."""
        trig, why = _trigger(before, run, words_start, explicit, distinct)
        if trig is None:
            return None, why
        need = MIN_WORDS[trig]
        if length < need:
            return None, "too_short"
        folds = tuple(t.fold for t in run[words_start:words_start + length])
        mass = span_mass(index, folds)
        cue = quran_cue(before, run[words_start].start)
        if trig == "distinct":
            if mass < MASS_CANDIDATE or any(_contains(folds, f) for f in _FORMULA_SET):
                return None, "too_common"
        elif need_mass and mass < MIN_MASS.get(length, DEFAULT_MIN_MASS) and not explicit:
            return None, "too_common"
        if any(_contains(folds, f) for f in _FORMULA_SET) and cue != "quran" and trig not in ("cue", "opener", "explicit"):
            return None, "formula"
        if len(places) > MAX_PLACES.get(length, DEFAULT_MAX_PLACES):
            return None, "ambiguous"
        return trig, None

    style = _Style(run)
    lead_space = " " if before and not before[-1].isspace() else ""   # right after a word, or after «،» / «؛» typed without a space

    # --- continuations: the typed words (all of them, complete) end inside a verse
    cont: list[_Place] = []
    # The whole run ends with a short match elsewhere while a much longer exact beginning (all but the last word) fits one verse:
    # the writer is quoting that verse and the last word is the odd one out. The short match is not a continuation.
    anchor_wins = best_anchor >= CORRECTION_MIN_WORDS and best_anchor >= best_full + ANCHOR_DOMINATES
    if best_full >= 2 and not anchor_wins:
        cont = [p for p in full if p.length == best_full]
        total_places = len(cont)
        trig, why = gate(cont, best_full, n - best_full)
        if trig:
            trigger = trig
            seen_v: set[tuple[int, int]] = set()
            blocked = "complete"
            for pl in cont:
                stream = index.streams[pl.surah]
                _, ayah_no, wi = stream[pl.pos]
                if (pl.surah, ayah_no) in seen_v:
                    continue
                seen_v.add((pl.surah, ayah_no))
                ch = _choice_from(index, pl.surah, ayah_no, wi + 1, wi + 1, pl, style, lead_space, best_full, "continue",
                                  (len(before), len(before)), "", "exact")
                if ch:
                    results.append(ch)
                    blocked = None
        else:
            blocked = why

    # --- the caret is inside the last word: it may be the beginning of the verse's next word
    if mid_word and n >= 2 and best_anchor >= 2:
        part = run[-1]
        pf = part.fold
        anchors = [p for p in anchor_places if p.length == best_anchor]
        wi_total = len(anchors)
        trig, why = gate(anchors, best_anchor, n - 1 - best_anchor)
        if trig:
            seen_v = set()
            for pl in anchors:
                stream = index.streams[pl.surah]
                if pl.pos + 1 >= len(stream):
                    continue
                nf, ayah_no, wi = stream[pl.pos + 1]
                if nf.startswith(pf) and nf != pf and len(pf) >= 1 and (pl.surah, ayah_no) not in seen_v:
                    seen_v.add((pl.surah, ayah_no))
                    ch = _choice_from(index, pl.surah, ayah_no, wi, wi, _Place(pl.surah, pl.pos + 1, pl.length + 1), style, "", best_anchor + 1,
                                      "complete_word", (part.start, part.end), part.raw, "exact")
                    if ch:
                        results.append(ch)
            if results and trigger is None:
                trigger = trig
                total_places = max(total_places, wi_total)

    # --- a different last word after a distinctive exact beginning: a probable correction
    wrong_fold = run[-1].fold if n else ""
    word_final = (not mid_word) or explicit or len(wrong_fold) >= MID_WORD_MIN_LETTERS   # a word still being typed is judged only when long enough
    if n >= 2 and word_final and best_anchor >= CORRECTION_MIN_WORDS and (best_full < 3 or anchor_wins):
        anchors = [p for p in anchor_places if p.length == best_anchor]
        folds = tuple(t.fold for t in run[n - 1 - best_anchor:n - 1])
        mass = span_mass(index, folds)
        trig, why = _trigger(before, run, n - 1 - best_anchor, explicit, distinct)
        if trig and mass >= CORRECTION_MIN_MASS and len(anchors) <= CORRECTION_MAX_PLACES and not any(_contains(folds, f) for f in _FORMULA_SET):
            wrong = run[-1]
            for pl in anchors:
                stream = index.streams[pl.surah]
                if pl.pos + 1 >= len(stream):
                    continue
                nf, ayah_no, wi = stream[pl.pos + 1]
                a = index.ayahs[(pl.surah, ayah_no)]
                if wi != stream[pl.pos][2] + 1 or _eq(wrong, nf):
                    continue  # the next word is in the following verse (the verse is complete) or the writer wrote it correctly
                if mid_word and nf.startswith(wrong.fold):
                    continue  # still a beginning of the verse word: the word-completion path handles it
                made = None
                for skip in range(1, SKIP_MAX + 1):
                    j = pl.pos + 1 + skip
                    if j < len(stream) and stream[j][1] == ayah_no and _eq(wrong, stream[j][0]):
                        words = a.words[wi:wi + skip]
                        made = ("insert", words)
                        break
                if made is None:
                    made = ("replace", [a.words[wi]])
                kind, words = made
                to_text = style.words(words)
                first_ayah = stream[pl.pos - pl.length + 1][1]
                ch = {
                    "kind": kind, "certainty": "probable",
                    "replace_start": wrong.start, "replace_end": wrong.end if kind == "replace" else wrong.start,
                    "from_text": wrong.raw if kind == "replace" else "", "to_text": to_text,
                    "insert_text": to_text if kind == "replace" else to_text + " ",
                    "extend_text": None, "typed_words": best_anchor, "added_words": len(words), "remaining_words": 0,
                    "surah": pl.surah, "surah_name": NAMES.get(pl.surah, str(pl.surah)), "ayah_start": first_ayah, "ayah_end": ayah_no,
                    "label": _label(pl.surah, first_ayah, ayah_no),
                    "verse": _verse_block(index, pl.surah, ayah_no, (max(0, wi - best_anchor), wi), (wi, wi + len(words))),
                }
                if not any(r["surah"] == ch["surah"] and r["ayah_end"] == ch["ayah_end"] and r["kind"] == kind for r in results):
                    results.append(ch)
            if results:
                trigger = trig
                total_places = max(total_places, len(anchors))
        elif not results:
            blocked = blocked or why

    # a continuation of the exact text already written in `after` is not suggested again
    if after_fold is not None:
        kept = [r for r in results if r["kind"] != "continue" or not r["to_text"] or arabic.tokenize(r["to_text"])[0].fold != after_fold]
        if results and not kept:
            blocked = "already_present"
        results = kept

    if not results:
        if explicit:
            reason = "too_short" if n < 2 else (blocked or "no_match")
            return {**base, "status": "hint", "reason": reason, "places": total_places}
        return none(blocked or ("no_match" if best_full >= 2 or best_anchor >= 2 else "no_trigger"), places=total_places)

    rank = {"continue": 0, "complete_word": 0, "insert": 1, "replace": 2}
    results.sort(key=lambda r: (rank[r["kind"]], -r["typed_words"], r["surah"], r["ayah_end"]))
    results = results[:MAX_CHOICES]
    texts = {re.sub(r"\s+", " ", arabic.folded(r["to_text"])) for r in results}
    places = {(r["surah"], r["ayah_start"], r["ayah_end"]) for r in results}
    return {**base, "status": "suggest", "trigger": trigger, "choices": results, "places": max(total_places, len(places)),
            "ambiguous": len(texts) > 1 or len(places) > 1}
