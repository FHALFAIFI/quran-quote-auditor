"""Deterministic detection and parsing of surah/ayah references.

Recognised forms (Arabic-Indic or Latin digits):

* ``البقرة: 255`` / ``[البقرة: 255]`` / ``(البقرة ٢٥٥)`` / ``البقرة/255``
* ``سورة البقرة، الآية 255`` / ``سورة البقرة آية 255-257``
* ``الآية 255 من سورة البقرة``
* ``2:255`` / ``[2:255-257]``
* ``سورة البقرة`` (surah only)

Parsing runs on a folded copy of the text (diacritics removed, hamza/alef
variants folded) and maps spans back to the original offsets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .arabic import folded, fold_with_map
from .surahs import ALIASES, AYAH_COUNTS, NAMES


@dataclass
class Reference:
    start: int
    end: int
    text: str
    surah: int
    ayah_start: int | None = None
    ayah_end: int | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.problems

    def label(self) -> str:
        name = NAMES.get(self.surah, str(self.surah))
        if self.ayah_start is None:
            return f"سورة {name}"
        if self.ayah_end and self.ayah_end != self.ayah_start:
            return f"{name}: {self.ayah_start}–{self.ayah_end}"
        return f"{name}: {self.ayah_start}"

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "surah": self.surah,
            "surah_name": NAMES.get(self.surah),
            "ayah_start": self.ayah_start,
            "ayah_end": self.ayah_end,
            "label": self.label(),
            "problems": self.problems,
        }


def _name_table() -> dict[str, int]:
    table: dict[str, int] = {}
    for num, name in NAMES.items():
        variants = {name, *ALIASES.get(num, [])}
        for v in variants:
            table.setdefault(folded(v), num)
    return table


_NAMES_FOLDED = _name_table()
# Longest names first so "ال عمران" wins over shorter prefixes.
_NAME_ALT = "|".join(re.escape(n) for n in sorted(_NAMES_FOLDED, key=len, reverse=True))
_L = r"ء-ي"  # Arabic letters in folded text
_NUM = r"(\d{1,3})"
_RANGE = rf"{_NUM}(?:\s*[-–—]\s*{_NUM})?"
_AYAH_WORD = r"(?:الايه|الايات|ايه|ايات|اية|الاية|رقم)"

# سورة X[،:]? [الآية]? N[-M]
_P_SURAH_WORD = re.compile(
    rf"(?<![{_L}])سوره\s+(?P<name>{_NAME_ALT})(?![{_L}])"
    rf"(?:\s*[،,:؛\-–]?\s*(?:{_AYAH_WORD}\s*)?[:(\[]?\s*{_RANGE})?"
)
# X: N  or  X N (bare name needs a separator or the word آية before the number)
_P_BARE = re.compile(
    rf"(?<![{_L}])(?P<name>{_NAME_ALT})(?![{_L}])\s*(?:[:：/،,]\s*(?:{_AYAH_WORD}\s*)?|\s+{_AYAH_WORD}\s*[:]?\s*|\s+(?=\d))\s*{_RANGE}"
)
# الآية N من سورة X
_P_AYAH_FIRST = re.compile(
    rf"(?<![{_L}]){_AYAH_WORD}\s*(?:رقم\s*)?[:(]?\s*{_RANGE}\s*\)?\s*(?:من|في)\s+سوره\s+(?P<name>{_NAME_ALT})(?![{_L}])"
)
# الآية الخامسة عشرة من سورة X — an ayah number written as a (feminine) ordinal word, 1–99, only before «من/في سورة …»
def _ordinal_table() -> dict[str, int]:
    first = ["الأولى", "الثانية", "الثالثة", "الرابعة", "الخامسة", "السادسة", "السابعة", "الثامنة", "التاسعة", "العاشرة"]
    unit = ["الحادية", "الثانية", "الثالثة", "الرابعة", "الخامسة", "السادسة", "السابعة", "الثامنة", "التاسعة"]
    tens = {20: ("العشرون", "العشرين"), 30: ("الثلاثون", "الثلاثين"), 40: ("الأربعون", "الأربعين"), 50: ("الخمسون", "الخمسين"),
            60: ("الستون", "الستين"), 70: ("السبعون", "السبعين"), 80: ("الثمانون", "الثمانين"), 90: ("التسعون", "التسعين")}
    words: dict[str, int] = {w: n for n, w in enumerate(first, 1)}
    words.update({f"{w} عشرة": 10 + n for n, w in enumerate(unit, 1)})
    for t, forms in tens.items():
        for f in forms:
            words[f] = t
            words.update({f"{u} و{f}": t + n for n, u in enumerate(unit, 1)})
    return {" ".join(folded(x) for x in k.split()): v for k, v in words.items()}


_ORDINALS = _ordinal_table()
_ORD_ALT = "|".join(re.escape(w) for w in sorted(_ORDINALS, key=len, reverse=True))
_P_AYAH_ORDINAL = re.compile(
    rf"(?<![{_L}]){_AYAH_WORD}\s+(?P<ord>{_ORD_ALT})(?![{_L}])\s*(?:من|في)\s+سوره\s+(?P<name>{_NAME_ALT})(?![{_L}])"
)
# 2:255 or 2:255-257
_P_NUMERIC = re.compile(rf"(?<![\d:.])(\d{{1,3}})\s*:\s*{_RANGE}(?![\d:])")


def _validate(ref: Reference) -> None:
    if not 1 <= ref.surah <= 114:
        ref.problems.append("رقم السورة خارج النطاق 1–114")
        return
    count = AYAH_COUNTS[ref.surah]
    for a in (ref.ayah_start, ref.ayah_end):
        if a is not None and not 1 <= a <= count:
            ref.problems.append(f"سورة {NAMES[ref.surah]} عدد آياتها {count}، والرقم {a} خارج النطاق")
            break
    if ref.ayah_start and ref.ayah_end and ref.ayah_end < ref.ayah_start:
        ref.problems.append("نهاية النطاق أصغر من بدايته")


def _span(idx: list[int], fs: int, fe: int) -> tuple[int, int]:
    return idx[fs], idx[fe - 1] + 1


def find_references(text: str) -> list[Reference]:
    """Find all references in ``text``; overlapping matches keep the longest."""
    ftext, idx = fold_with_map(text)
    found: list[tuple[int, int, Reference]] = []

    def add(m: re.Match, surah: int, a1: str | None, a2: str | None) -> None:
        fs, fe = m.span()
        # trim trailing spaces/punctuation from the folded span
        while fe > fs and ftext[fe - 1] in " ،,:؛([":
            fe -= 1
        s, e = _span(idx, fs, fe)
        ref = Reference(
            start=s,
            end=e,
            text=text[s:e],
            surah=surah,
            ayah_start=int(a1) if a1 else None,
            ayah_end=int(a2) if a2 else None,
        )
        _validate(ref)
        found.append((fs, fe, ref))

    for m in _P_AYAH_FIRST.finditer(ftext):
        add(m, _NAMES_FOLDED[m.group("name")], m.group(1), m.group(2))
    for m in _P_AYAH_ORDINAL.finditer(ftext):
        add(m, _NAMES_FOLDED[m.group("name")], str(_ORDINALS[m.group("ord")]), None)
    for m in _P_SURAH_WORD.finditer(ftext):
        add(m, _NAMES_FOLDED[m.group("name")], m.group(2), m.group(3))
    for m in _P_BARE.finditer(ftext):
        add(m, _NAMES_FOLDED[m.group("name")], m.group(2), m.group(3))
    for m in _P_NUMERIC.finditer(ftext):
        add(m, int(m.group(1)), m.group(2), m.group(3))

    # Resolve overlaps: prefer longer spans, then earlier.
    found.sort(key=lambda t: (-(t[1] - t[0]), t[0]))
    chosen: list[tuple[int, int, Reference]] = []
    for fs, fe, ref in found:
        if all(fe <= cs or fs >= ce for cs, ce, _ in chosen):
            chosen.append((fs, fe, ref))
    chosen.sort(key=lambda t: t[0])
    return [r for _, _, r in chosen]


def parse_reference(text: str) -> Reference | None:
    refs = find_references(text)
    return refs[0] if refs else None
