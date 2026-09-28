"""Arabic text normalization used for *searching* only.

Three comparison levels are kept deliberately separate so the verifier can
tell the user which kind of match it found:

* ``literal``  – NFC text with annotation marks (Quranic pause/sajdah/hizb
  signs), tatweel, zero-width characters and BOMs removed. Letters and
  diacritics (harakat, shadda, sukun, dagger alef) are kept.
* ``letters``  – all diacritics removed; every letter form (hamza seats,
  alef maqsura, taa marbuta …) is kept exactly.
* ``folded``   – ``letters`` plus folding of common script/spelling variants
  (أ إ آ ٱ → ا, ى → ي, ة → ه, ؤ → و, ئ → ي, Persian/Urdu letter forms, …).

``folded`` is what the index searches on. A match found only at ``folded``
level is never reported as a literal match.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Quranic annotation marks: small high ligatures / pause signs, end-of-ayah,
# rub el hizb, sajdah, small waw/yeh etc. They are not part of the wording.
_ANNOTATION = set(range(0x06D6, 0x06DD)) | {0x06DD, 0x06DE, 0x06E9} | set(range(0x06DF, 0x06E5)) | set(range(0x06E7, 0x06E9)) | set(range(0x06EA, 0x06EE))
# Invisible / typographic characters.
_INVISIBLE = {0xFEFF, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x061C, 0x2066, 0x2067, 0x2068, 0x2069, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E}
TATWEEL = 0x0640
# Vowel/diacritic marks (harakat, tanween, shadda, sukun, maddah, hamza marks,
# dagger alef, small high/low letters used as vowels).
_DIACRITICS = set(range(0x064B, 0x0660)) | {0x0670, 0x06E5, 0x06E6}

_FOLD = {
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ٲ": "ا", "ٳ": "ا",
    "ى": "ي", "ی": "ي", "ې": "ي", "ۍ": "ي",
    "ة": "ه", "ۀ": "ه", "ە": "ه",
    "ؤ": "و",
    "ئ": "ي",
    "ک": "ك", "ڪ": "ك",
    "ﻻ": "لا",
}
_LIGATURES = {"ﷲ": "الله", "ﷺ": "صلى الله عليه وسلم"}

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def to_ascii_digits(s: str) -> str:
    return s.translate(_DIGITS)


def is_arabic_letter(ch: str) -> bool:
    o = ord(ch)
    return (0x0620 <= o <= 0x064A) or (0x066E <= o <= 0x06D3) or o == 0x06D5 or (0x06EE <= o <= 0x06FF and o not in (0x06F0, 0x06F1, 0x06F2, 0x06F3, 0x06F4, 0x06F5, 0x06F6, 0x06F7, 0x06F8, 0x06F9))


def is_diacritic(ch: str) -> bool:
    return ord(ch) in _DIACRITICS


def is_ignorable(ch: str) -> bool:
    o = ord(ch)
    return o in _ANNOTATION or o in _INVISIBLE or o == TATWEEL


def _expand_ligatures(text: str) -> str:
    for k, v in _LIGATURES.items():
        text = text.replace(k, v)
    return text


def literal(text: str) -> str:
    """Letters + diacritics, annotation marks and tatweel removed, NFC."""
    text = unicodedata.normalize("NFC", _expand_ligatures(text))
    out = [ch for ch in text if not is_ignorable(ch)]
    return re.sub(r"\s+", " ", "".join(out)).strip()


def letters(text: str) -> str:
    """Remove diacritics as well; keep letter forms exactly."""
    return "".join(ch for ch in literal(text) if not is_diacritic(ch))


def fold_char(ch: str) -> str:
    return _FOLD.get(ch, ch)


def folded(text: str) -> str:
    return "".join(fold_char(ch) for ch in letters(text))


@dataclass(frozen=True)
class Token:
    """A word of the submitted text with its span in the original string."""

    start: int
    end: int
    raw: str  # original substring
    fold: str  # folded form used for search


def tokenize(text: str) -> list[Token]:
    """Split text into Arabic word tokens, keeping original offsets.

    A token is a maximal run of Arabic letters, diacritics and ignorable marks
    that contains at least one letter. Everything else (spaces, punctuation,
    brackets, digits, Latin text) separates tokens.
    """
    tokens: list[Token] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if is_arabic_letter(ch) or ch in _LIGATURES:
            j = i
            while j < n and (is_arabic_letter(text[j]) or is_diacritic(text[j]) or is_ignorable(text[j]) or text[j] in _LIGATURES):
                j += 1
            raw = text[i:j]
            f = folded(raw)
            if f:
                if " " in f:  # expanded ligature such as ﷺ
                    for part in f.split(" "):
                        tokens.append(Token(i, j, raw, part))
                else:
                    tokens.append(Token(i, j, raw, f))
            i = j
        else:
            i += 1
    return tokens


def fold_with_map(text: str) -> tuple[str, list[int]]:
    """Fold text for regex scanning and return a map folded-index → original-index.

    Diacritics and ignorable marks are dropped, letters folded, digits made
    ASCII, runs of whitespace collapsed to one space. Other characters are kept.
    """
    out: list[str] = []
    idx: list[int] = []
    prev_space = False
    for i, ch in enumerate(text):
        if is_diacritic(ch) or is_ignorable(ch):
            continue
        if ch.isspace():
            if prev_space:
                continue
            out.append(" ")
            idx.append(i)
            prev_space = True
            continue
        prev_space = False
        c = to_ascii_digits(fold_char(ch))
        out.append(c)
        idx.append(i)
    return "".join(out), idx


def diacritic_profile(word: str) -> list[tuple[str, frozenset[str]]]:
    """Return [(base letter, set of diacritics on it)] for a single word."""
    word = literal(word)
    prof: list[tuple[str, set[str]]] = []
    for ch in word:
        if is_diacritic(ch):
            if prof:
                prof[-1][1].add(ch)
        elif not ch.isspace():
            prof.append((ch, set()))
    return [(b, frozenset(m)) for b, m in prof]


def has_diacritics(text: str) -> bool:
    return any(is_diacritic(ch) for ch in text)
