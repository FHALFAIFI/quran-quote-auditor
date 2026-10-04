"""Deterministic extraction of *explicitly marked* quotations (no AI).

Accepted markers:

* ornate Quranic brackets ﴿…﴾ (either order) and curly braces {…} — always;
* «…», "…", “…”, ((…)) — only when preceded by a Quran cue such as
  "قال تعالى" or followed closely by a surah/ayah reference.
"""

from __future__ import annotations

import re

from ..arabic import folded, tokenize
from ..references import Reference
from .base import Candidate

_ORNATE = "\ufd3e\ufd3f"  # ﴾ ﴿ — writers use them in either order
_ALWAYS = [
    (re.compile(r"\{([^{}]{2,1500})\}"), "{}"),
]
_CONDITIONAL = [
    (re.compile(r"«([^«»]{2,1500})»"), "«»"),
    (re.compile(r"\"([^\"\n]{2,1500})\""), '""'),
    (re.compile(r"“([^“”\n]{2,1500})”"), "“”"),
    (re.compile(r"”([^“”\n]{2,1500})“"), "“”"),
    (re.compile(r"\(\(([^()]{2,1500})\)\)"), "(())"),
]
_CUES = [folded(c) for c in (
    "قال تعالى", "قوله تعالى", "يقول تعالى", "وقال تعالى", "تعالى", "سبحانه", "عز وجل", "جل وعلا",
    "جل جلاله", "قال الله", "يقول الله", "قول الله", "القرآن", "الآية", "آية", "في كتابه",
)]


def _has_cue(article: str, start: int) -> bool:
    before = folded(article[max(0, start - 40):start])
    return any(c in before for c in _CUES)


def _has_ref_after(end: int, refs: list[Reference]) -> bool:
    return any(0 <= r.start - end <= 25 for r in refs)


def _ornate_pairs(article: str) -> list[tuple[int, int]]:
    """Pair ornate brackets sequentially: an opener is closed by the *other* bracket.

    Pairing in order (rather than by a fixed opener) handles texts that type
    ﴿…﴾ as well as ﴾…﴿, without matching the gap *between* two quotations.

    A run of the same bracket typed twice («﴿﴿ … ﴾﴾») counts as one bracket: read one by one it would put the pairing out of
    step, and the gap between two quotations would become one long "quotation". A pair never spans a blank line.
    """
    pairs: list[tuple[int, int]] = []
    open_pos, open_ch = -1, ""
    prev = ""
    for i, ch in enumerate(article):
        if ch not in _ORNATE:
            if not ch.isspace():
                prev = ""
            continue
        if ch == prev:
            continue  # the same bracket repeated: still the one already seen
        prev = ch
        if open_pos >= 0 and ch != open_ch and i - open_pos <= 1500 and "\n\n" not in article[open_pos:i]:
            pairs.append((open_pos + 1, i))
            open_pos, open_ch = -1, ""
        else:
            open_pos, open_ch = i, ch
    return pairs


def _candidate(article: str, s: int, e: int, marker: str) -> Candidate | None:
    toks = tokenize(article[s:e])
    if len(toks) < 2:
        return None
    # trim to the Arabic words inside the marker
    cs, ce = s + toks[0].start, s + toks[-1].end
    return Candidate(cs, ce, article[cs:ce], {"marked"}, marker)


def extract_marked(article: str, refs: list[Reference]) -> list[Candidate]:
    out: list[Candidate] = []
    for s, e in _ornate_pairs(article):
        if c := _candidate(article, s, e, "﴿﴾"):
            out.append(c)
    for patterns, conditional in ((_ALWAYS, False), (_CONDITIONAL, True)):
        for rx, marker in patterns:
            for m in rx.finditer(article):
                if conditional and not (_has_cue(article, m.start()) or _has_ref_after(m.end(), refs)):
                    continue
                if c := _candidate(article, *m.span(1), marker):
                    out.append(c)
    return out
