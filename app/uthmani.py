"""Documented Uthmani-script (rasm) equivalences, used when a quotation is copied from a mushaf site or app.

The source text (Quranpedia, mushaf 1) is written in standard "imla'i" spelling with full vocalisation. Printed mushafs
and Quran apps write the same words in the Uthmani rasm (``ٱلصَّلَوٰةَ`` for ``الصَّلَاةَ``). The ordinary folding in
``arabic`` does not equate these spellings, so a correct copy used to be reported as a wording difference.

This module is deliberately narrow. Every convention it recognises is an explicit rule or a short closed word list (below),
it is applied only to a word that shows an Uthmani feature (``ٱ``, a small high Quranic mark, a tatweel carrying a mark, a
dagger alef, a separate hamza before alef ...), and a word without such a feature is folded exactly as before. It does
NOT erase hamzas, replace every و by ا, discard vocalisation, or accept a word because it is "close": a word is
equivalent to a source word only when the transformed letters are *identical* to the source's (after the ordinary fold).
A word that no rule explains is not equivalent; the verifier then calls it a difference, or "uncertain" when it has the
same consonant skeleton as the source word (``same_skeleton``), and never proposes a replacement for it.

Recognised conventions (codes in ``wording.script.features``):

``wasla``            ٱ for ا
``small_marks``      small high/low Quranic marks (ۡ ۟ ۠ ۢ ...): not part of the wording
``dagger_alef``      a dagger alef ٰ for a long ā that the imla'i spelling writes as ا (ٱلْكِتَٰب = الْكِتَاب), also ىٰ → ا before a
                     suffix (ٱشْتَرَىٰهُ = اشْتَرَاهُ); the imla'i text keeps ٰ for a closed list of words (هَٰذَا ذَٰلِكَ لَٰكِن إِلَٰه ...)
``waw_alef``         و carrying a dagger alef for ا in a closed list (ٱلصَّلَوٰة ٱلزَّكَوٰة ٱلْحَيَوٰة مِشْكَوٰة مَنَوٰة ٱلْغَدَوٰة ٱلنَّجَوٰة ٱلرِّبَوٰا)
``hamza_alef``       ء with fatha before ا (ءَامَنُوا, ءَايَٰت, بِـَٔايَٰت) for آ
``hamza_seat``       a hamza written without its seat letter (ء or on a tatweel): the seat of the imla'i text, by the standard rule
``small_letters``    a small waw/yeh/alef mark that the imla'i text writes as a letter (دَاوُۥد, ٱلنَّبِيِّـۧن, يَسْتَحْيِۦ)
``madd_sign``        آ or ٓ written for the long ā (لَآ إِنَّمَآ جَآءَ): a prolongation sign, not another letter
``idgham_shadda``    a shadda on the first letter (لِّلْمُتَّقِينَ) or on the ta of دتّ (أَرَدتُّمْ): the printed rasm's mark of idgham,
                     which the imla'i text does not have; a mark, not a vowel
``vocative``         the vocative يَٰـ joined to the next word (يَٰٓأَيُّهَا = يَا أَيُّهَا), read as two words
``lam``              one lam (with shadda) written for two: ٱلَّيْل ٱلَّٰتِى (الليل اللاتي)
``silent_alef``      a silent alef the imla'i text omits (أُوْلُواْ = أُولُو)

Not covered: see docs/UTHMANI.md. Such a word is reported as "uncertain", without a replacement.
"""

from __future__ import annotations

from . import arabic

WASLA, DAGGER, TATWEEL, HAMZA = "ٱ", "ٰ", "ـ", "ء"
FATHA, DAMMA, KASRA, SUKUN, SHADDA = "َ", "ُ", "ِ", "ْ", "ّ"
FATHATAN, DAMMATAN, KASRATAN = "ً", "ٌ", "ٍ"
SMALL_WAW, SMALL_YEH, SMALL_HIGH_YEH, SUKUN_SMALL, SMALL_ZERO = "ۥ", "ۦ", "ۧ", "ۡ", "۟"
# Marks of the "idgham" tanween used in one printed Uthmani edition, read as the ordinary tanween they stand for.
_TANWEEN_VARIANT = {"ٖ": KASRATAN, "ٗ": FATHATAN, "ٞ": DAMMATAN}
_VOWELS = {FATHA: 1, DAMMA: 2, KASRA: 3, FATHATAN: 1, DAMMATAN: 2, KASRATAN: 3}
# Small Quranic marks that exist only in Uthmani-script text (pause signs, sajdah and hizb marks are in the imla'i text too).
_SMALL = {chr(c) for c in (0x06DF, 0x06E0, 0x06E1, 0x06E2, 0x06E3, 0x06E4, 0x06E5, 0x06E6, 0x06E7, 0x06E8, 0x06EA, 0x06EB, 0x06EC, 0x06ED)}
_INVISIBLE = {chr(c) for c in arabic._INVISIBLE}
_COMPOSE = {"ا": {"ٔ": "أ", "ٕ": "إ", "ٓ": "آ"}, "أ": {"ٓ": "آ"}, "و": {"ٔ": "ؤ"}, "ي": {"ٔ": "ئ"}, "ى": {"ٔ": "ئ"}}
WILD = "\ue000"  # an آ written as a madd sign: the imla'i text has ا (لَآ = لَا) or آ (the word's own آ)

# --- closed word lists (folded letters, no marks). Each list is checked against the whole Quranpedia text by
# --- eval/check_uthmani_rules.py; docs/UTHMANI.md states the result.
def _f(words) -> tuple[str, ...]:
    return tuple(arabic.folded(w) for w in words)


# The imla'i text KEEPS the dagger alef in these words (and their inflections, with clitic prefixes): هَٰذَا ذَٰلِكَ أُولَٰئِكَ لَٰكِن إِلَٰه ٱلرَّحْمَٰن.
_DAGGER_KEPT = _f(("ذلك", "هذا", "هذه", "هذان", "هذين", "هؤلاء", "اولئك", "لكن", "اله", "رحمن", "هكذا"))
# و carrying a dagger alef is ا in these words (matched inside the word once the dagger is dropped): stem → imla'i letters.
_WAW_ALEF = dict(zip(_f(("صلوة", "زكوة", "حيوة", "مشكوة", "منوة", "غدوة", "نجوة", "ربو")), _f(("صلاة", "زكاة", "حياة", "مشكاة", "مناة", "غداة", "نجاة", "ربا"))))
# One lam written for two at the start of the word (after one optional clitic): Uthmani letters → imla'i letters.
_LAM = dict(zip(_f(("اليل", "الات", "الاتي", "الائي", "الذان", "التان")), _f(("الليل", "اللات", "اللاتي", "اللائي", "اللذان", "اللتان"))))
# Whole-word spellings of the Uthmani rasm that differ from the imla'i text by one letter (checked on the whole text):
# the alef after a final stem-waw is not written in the imla'i text, and is written there where the rasm leaves it out.
_WORD_FIXES = dict(zip(_f(("اولوا", "رباا", "يحي", "يستحي", "اقصا", "محي", "تحي", "نحي", "احي")),
                       ("أولو", "ربا", "يحيي", "يستحيي", "أقصى", "محيي", "تحيي", "نحيي", "أحيي")))
_CLITICS = ("", "و", "ف", "ب", "ل", "ك", "ا", "ول", "فل", "وب", "فب", "وك", "وا", "فا", "وس", "فس", "س")


class _Unit:
    __slots__ = ("base", "marks", "start", "end", "tatweel_hamza", "merged")

    def __init__(self, base: str, start: int, end: int):
        self.base, self.marks, self.start, self.end, self.tatweel_hamza, self.merged = base, "", start, end, False, False

    @property
    def vowel(self) -> int:
        return max((_VOWELS.get(m, 0) for m in self.marks), default=0)

    @property
    def quiet(self) -> bool:  # no vowel of its own (a sukun, or silent)
        return self.vowel == 0 and SHADDA not in self.marks and DAGGER not in self.marks

    def vowel_marks(self) -> str:
        return "".join(m for m in self.marks if m in _VOWELS or m == SHADDA)


def _units(raw: str) -> list[_Unit]:
    """Base letters (a tatweel counts as one) with the marks written on them and their offsets in ``raw``."""
    out: list[_Unit] = []
    for i, ch in enumerate(raw):
        if ch in _INVISIBLE:
            if out:
                out[-1].end = i + 1
            continue
        if arabic.is_diacritic(ch) or ch in _SMALL or (arabic.is_ignorable(ch) and ch != TATWEEL):
            if out:
                out[-1].marks += _TANWEEN_VARIANT.get(ch, ch)
                out[-1].end = i + 1
            continue
        out.append(_Unit(ch, i, i + 1))
    for u in out:  # a vowel followed by a small meem is the tanween before ب (أَلِيمُۢ = أَلِيمٌ)
        if "ۢ" in u.marks or "ۭ" in u.marks:
            u.marks = u.marks.replace(FATHA, FATHATAN).replace(DAMMA, DAMMATAN).replace(KASRA, KASRATAN)
    for u in out:  # a hamza/madda mark written separately composes with its seat like NFC would
        if u.base in _COMPOSE and any(m in u.marks for m in _COMPOSE[u.base]):
            mark = next(m for m in _COMPOSE[u.base] if m in u.marks)
            u.base, u.marks = _COMPOSE[u.base][mark], u.marks.replace(mark, "")
    return out


def _is_final(us: list[_Unit], j: int) -> bool:
    """Nothing but a tanween alef follows unit j."""
    rest = us[j + 1:]
    return not rest or (len(rest) == 1 and rest[0].base == "ا")


def _lead(us: list[_Unit]) -> int:
    """Number of leading units that are clitic prefixes and/or the article: a hamza right after them starts the word proper."""
    j, n = 0, len(us)
    if j + 2 < n and us[j].base in "وف":
        j += 1
    if j + 2 < n and (us[j].base in "كل" or (us[j].base == "ب" and us[j].vowel == 3)):
        j += 1
    if j + 2 < n and us[j].base in "اٱ" and us[j + 1].base == "ل" and SHADDA not in us[j + 1].marks:
        j += 2
    return j


def _seat(us: list[_Unit], j: int) -> str:
    """The letter that carries the hamza at unit j in the imla'i text, by the standard seat rule (``ء`` when it sits on the line).

    A hamza written on a tatweel is always a hamza whose seat the rasm leaves out. A standalone ء is also written in the
    imla'i text itself (جُزْءًا سُوءٌ رُءُوس جَاءَ), so it is given a seat only where the imla'i text never writes it bare.
    """
    h, p, own = us[j], (us[j - 1] if j else None), us[j].vowel
    tat = h.tatweel_hamza
    by_vowel = {3: "ئ", 2: "ؤ", 1: "أ"}
    nxt = us[j + 1] if j + 1 < len(us) else None
    if p is None or j == _lead(us):
        return "إ" if own == 3 else "أ"
    if j == 1 and p.base in "أإؤئء":  # أَءِنَّا: a second hamza after the question hamza sits on alef
        return "إ" if own == 3 else "أ"
    if p.base == "ي" and p.quiet and own == 1 and nxt is not None and nxt.base == "ا":  # شَيْئًا هَنِيئًا: on the yeh seat
        return "ئ"
    if own == 2 and nxt is not None and nxt.base == "و" and (p.base == "ر" or p.base in "اآ" or DAGGER in p.marks):  # رَءُوف رُءُوس جَاءُوا
        return HAMZA
    if p.base in "اآ" or DAGGER in p.marks:  # after a long ā: on the line, except a kasra or a damma that is not final
        if own == 1 or _is_final(us, j):
            return HAMZA
        return by_vowel.get(own, HAMZA)
    if p.base in "وي" and p.quiet and j >= 2 and us[j - 2].vowel == (2 if p.base == "و" else 3):  # after a long ū / ī
        if not tat or _is_final(us, j):
            return HAMZA
        return "ئ" if p.base == "ي" else by_vowel.get(own, HAMZA)
    if p.quiet:  # after a sukun
        if not tat or _is_final(us, j):
            return HAMZA
        if p.base == "ي":  # كَهَيْئَة شَيْئًا, but يَيْأَس
            return "أ" if nxt is not None and nxt.base == "س" else "ئ"
        if own == 2 and nxt is not None and nxt.base == "و":  # مَسْئُولًا
            return "ئ"
        return by_vowel.get(own, HAMZA)
    if p.base == "و" and own == 1:  # تَبَوَّءُوا
        return HAMZA
    if tat and own == 2 and nxt is not None and nxt.base == "و" and p.vowel == 1:  # يَئُوده يَطَئُونَ يَئُوسًا
        return "ئ"
    if own == 2 and nxt is not None and nxt.base == "و" and p.vowel == 1 and not tat:  # بَدَءُوكُمْ
        return HAMZA
    return by_vowel.get(max(own, p.vowel), HAMZA)


def _hamza_cases(us: list[_Unit]) -> list[int]:
    """Indexes of hamzas written without a seat letter that need one in the imla'i text."""
    return [j for j, u in enumerate(us) if u.base == HAMZA and (u.tatweel_hamza or _seat(us, j) != HAMZA)]


def _expand_tatweel(us: list[_Unit]) -> list[_Unit]:
    """A tatweel is a carrier for a hamza, a small yeh or a dagger alef; any other tatweel is only a stretch."""
    out: list[_Unit] = []
    for u in us:
        if u.base != TATWEEL:
            out.append(u)
        elif "ٔ" in u.marks:
            h = _Unit(HAMZA, u.start, u.end)
            h.marks, h.tatweel_hamza = "".join(m for m in u.marks if m in _VOWELS), True
            if DAGGER in u.marks:
                h.marks += DAGGER
            out.append(h)
        elif SMALL_HIGH_YEH in u.marks:
            out.append(_Unit("ي", u.start, u.end))
        elif DAGGER in u.marks:
            c = _Unit("", u.start, u.end)  # a bare carrier of the dagger alef
            c.marks = u.marks
            out.append(c)
    return out


def _joins_alef(us: list[_Unit], k: int) -> bool:
    """Unit k is a hamza with fatha that the imla'i text writes together with the alef after it as آ."""
    u, nxt, p = us[k], (us[k + 1] if k + 1 < len(us) else None), (us[k - 1] if k else None)
    if u.base != HAMZA or not (FATHA in u.marks or DAGGER in u.marks):
        return False
    if DAGGER not in u.marks and not (nxt is not None and (nxt.base in "اآ" or (nxt.base == "" and DAGGER in nxt.marks))):
        return False
    if p is None or k == _lead(us) or p.quiet:
        return True
    if p.vowel == 1:  # مَآب
        return True
    return p.vowel == 3 and k == 1 and not p.marks.count(SHADDA)  # بِآيَات لِآدَم


def features(raw: str) -> list[str]:
    """Codes of the Uthmani-script features of a word ([] if it is written in ordinary spelling)."""
    us = _units(raw)
    f: list[str] = []
    if WASLA in raw:
        f.append("wasla")
    if any(c in _SMALL for c in raw):
        f.append("small_marks")
    if any(DAGGER in u.marks and not (u.base == "ى" and k == len(us) - 1) for k, u in enumerate(us)):
        f.append("dagger_alef")
    if any(u.base == "ا" and SUKUN in u.marks for u in us):
        f.append("silent_alef")
    ex = _expand_tatweel(us)
    if any(u.base == TATWEEL for u in us[1:]) and not f:
        f.append("tatweel")
    if _hamza_cases(ex) or any(_joins_alef(ex, k) for k in range(len(ex))):
        f.append("hamza_seat")
    letters = arabic.folded("".join(u.base for u in us))
    if "ٓ" in raw or any(u.base == "آ" and k > 0 and us[k - 1].vowel == 1 for k, u in enumerate(us)):
        f.append("madd_sign")  # آ (or ٓ) written for the long ā: لَآ إِنَّمَآ جَآءَ
    if us and SHADDA in us[0].marks:
        f.append("idgham_shadda")  # a shadda on the first letter marks the assimilation of the sound before it (the imla'i text has none)
    elif any(u.base == "ت" and SHADDA in u.marks and k and us[k - 1].base in "دطث" and not us[k - 1].marks for k, u in enumerate(us)):
        f.append("idgham_shadda")  # أَرَدتُّمْ فَرَّطتُّمْ: the dal/ta before it has no sukun mark and the ta carries the shadda
    if not f and (_word_fix_key(letters) or letters.endswith("اءو")):
        f.append("lexicon")
    return f


def _vocative_end(us: list[_Unit]) -> int:
    """Index of the unit that ends a joined vocative يَٰـ (``يَٰٓأَيُّهَا``, ``وَيَٰقَوْمِ``) or the joined ها of هَٰٓأَنتُمْ, or -1."""
    k = 1 if us and us[0].base in "وف" else 0
    if len(us) < k + 3 or us[k].base not in "يه":
        return -1
    carrier = k if DAGGER in us[k].marks else (k + 1 if us[k + 1].base == TATWEEL and DAGGER in us[k + 1].marks else -1)
    if carrier < 0:
        return -1
    if us[k].base == "ه":  # ها + أنتم / أنتما (هَٰٓؤُلَآء is one word and stays one)
        return carrier if carrier + 1 < len(us) and us[carrier + 1].base == "أ" else -1
    return carrier


def split_vocative(raw: str) -> list[tuple[int, int]]:
    """Character ranges of ``raw``: two for a joined vocative (يَٰٓأَيُّهَا → يَٰٓ + أَيُّهَا), else one."""
    us = _units(raw)
    k = _vocative_end(us)
    if k < 0 or k + 1 >= len(us):
        return [(0, len(raw))]
    cut = us[k].end
    return [(0, cut), (cut, len(raw))]


_PREFIX_LETTERS = "وفبلكأا"
_PREFIXES = {x + z for n in range(4) for x in ("".join(t) for t in __import__("itertools").product(_PREFIX_LETTERS, repeat=n)) for z in ("", "ال", "لل")}


def _kept(stem: str) -> bool:
    """The imla'i text keeps the dagger alef in this word (see ``_DAGGER_KEPT``): the stem, a short prefix and a short suffix."""
    for k in _DAGGER_KEPT:
        i = stem.find(k)
        while i != -1:
            if stem[:i] in _PREFIXES and len(stem) - i - len(k) <= 3:
                return True
            i = stem.find(k, i + 1)
    return False


def _see(us: list[_Unit]) -> list[_Unit]:
    """رَءَا → رَأَى (and with a pronoun suffix): the verb 'to see' is written with ء + ا where the imla'i text has أ + ى."""
    lead = _lead(us)
    if len(us) >= lead + 3 and us[lead].base == "ر" and us[lead + 1].base == HAMZA and us[lead + 2].base in "اآ":
        rest = "".join(u.base for u in us[lead + 3:])
        if rest == "":
            h, a = us[lead + 1], us[lead + 2]
            h.base, a.base = "أ", "ى"
            return us
    return us


def to_imlai(raw: str) -> tuple[list[tuple[str, str]], set[str]] | None:
    """The word in imla'i shape, ``([(letter, vowel marks)], rules that fired)``, or None if it shows no Uthmani feature.

    The letters are what the imla'i text writes (before the ordinary fold); only vowel marks and shadda are kept.
    """
    if not features(raw):
        return None
    rules: set[str] = set()
    us = _see(_expand_tatweel(_units(raw)))
    if any(u.tatweel_hamza for u in us):
        rules.add("hamza_seat")
    merged: list[_Unit] = []
    k = 0
    while k < len(us):
        if _joins_alef(us, k):
            own_dagger = DAGGER in us[k].marks
            m = _Unit("آ", us[k].start, us[k + (0 if own_dagger else 1)].end)
            m.merged = True
            m.marks = us[k].marks.replace(DAGGER, "").replace(FATHA, "") if own_dagger else us[k + 1].marks.replace(DAGGER, "")
            merged.append(m)
            rules.add("hamza_alef")
            k += 1 if own_dagger else 2
            continue
        merged.append(us[k])
        k += 1
    us = merged
    # a yeh carrying the small zero is silent: the imla'i text does not write it (أَفَإِي۟ن, نَبَإِي۟)
    us = [u for j, u in enumerate(us) if not (u.base == "ا" and (SMALL_ZERO in u.marks or SUKUN in u.marks) and j + 1 < len(us) and us[j + 1].base == "ي" and us[j + 1].quiet)]
    kept_us: list[_Unit] = []
    for u in us:
        if SMALL_ZERO in u.marks and u.base in "يى":
            if kept_us and kept_us[-1].base == "إ" and len(kept_us) >= 3 and kept_us[-2].base == "ل" and kept_us[-3].base == "م":
                kept_us[-1].base = "ئ"  # وَمَلَإِي۟هِ = وَمَلَئِهِ
            continue
        kept_us.append(u)
    us = kept_us
    for u in us:
        if u.base == "ص" and "ۜ" in u.marks:  # يَبْصُۜط: ص written, س read
            u.base = "س"
            rules.add("small_letters")
    # فَسْـَٔلْ وَسْـَٔلُوا: the alef wasla after و / ف is not written in the rasm
    if len(us) >= 3 and us[0].base in "وف" and us[1].base == "س" and us[1].quiet and us[2].tatweel_hamza:
        us.insert(1, _Unit("ا", us[1].start, us[1].start))
        rules.add("hamza_seat")
    # small waw / yeh written as letters (not the pronoun's long vowel on a final ه)
    exp: list[_Unit] = []
    for j, u in enumerate(us):
        exp.append(u)
        for small, letter in ((SMALL_WAW, "و"), (SMALL_YEH, "ي")):
            if small in u.marks and not (u.base == "ه" and j == len(us) - 1):
                exp.append(_Unit(letter, u.end, u.end))
                rules.add("small_letters")
    us = exp
    # a hamza written without its seat letter gets the imla'i seat
    for j in _hamza_cases(us):
        seat = _seat(us, j)
        if seat != us[j].base:
            us[j].base = seat
            rules.add("hamza_seat")
    if len(us) >= 2 and us[-1].base == "ا" and us[-2].base == "أ" and FATHATAN in us[-2].marks:
        us.pop()
    # final ؤ + silent alef: the imla'i text has أ after a fatha and ء after a long ā
    if len(us) >= 2 and us[-1].base == "ا" and us[-2].base == "ؤ":
        before = us[-3] if len(us) >= 3 else None
        us[-2].base = (HAMZA if before is not None and (before.base in "اآ" or DAGGER in before.marks)
                       else "ؤ" if before is not None and before.vowel == 2 else "أ")
        us.pop()
        rules.add("hamza_seat")
    # dagger alef
    stem = arabic.folded("".join(u.base for u in us if u.base))
    kept = _kept(stem)
    waw_word = next((w for w in _WAW_ALEF if w in stem), None)
    out: list[tuple[str, str]] = []
    n = len(us)
    for j, u in enumerate(us):
        if DAGGER not in u.marks:
            if u.base == "آ" and not u.merged and j > 0 and us[j - 1].vowel == 1:
                out.append((WILD, u.vowel_marks()))
            elif u.base:
                out.append((u.base, u.vowel_marks()))
            continue
        rules.add("dagger_alef")
        vm = u.vowel_marks()
        if u.base == "ى" and j == n - 1:
            out.append(("ى", vm))
        elif kept:
            if u.base:
                out.append((u.base, vm))
        elif u.base == "ى":
            out.append(("ا", ""))
        elif u.base == "و" and waw_word and not vm.strip(SHADDA):
            out.append(("ا", ""))
            rules.add("waw_alef")
        else:
            if u.base:
                out.append((u.base, vm))
            out.append(("ا", ""))
    if WASLA in raw:
        rules.add("wasla")
    if any(c in _SMALL for c in raw):
        rules.add("small_marks")
    rules.update(c for c in features(raw) if c in ("madd_sign", "idgham_shadda"))
    return _lexicon(out, rules), rules


def _lexicon(units: list[tuple[str, str]], rules: set[str]) -> list[tuple[str, str]]:
    letters = arabic.folded("".join(b for b, _ in units))
    for c in _CLITICS:
        if not letters.startswith(c):
            continue
        body = letters[len(c):]
        for u_form in _LAM:
            if body.startswith(u_form) and len(body) <= len(u_form) + 3:
                units = units[:len(c) + 1] + [("ل", "")] + units[len(c) + 1:]  # the lam that carries the shadda is written once for two
                rules.add("lam")
                letters = arabic.folded("".join(b for b, _ in units))
                break
        else:
            continue
        break
    key = _word_fix_key(letters)
    if key:
        prefix, wrong = key
        right = _WORD_FIXES[wrong]
        units = units[:len(prefix)] + [(ch, "") for ch in right]  # vowel marks are not compared for this word
        rules.add("word_spelling")
    return units


def _word_fix_key(letters: str) -> tuple[str, str] | None:
    """(prefix, spelling) when the word is one of the spellings in ``_WORD_FIXES`` after clitics and the article."""
    for c in _CLITICS:
        for art in ("", "ال", "لل"):
            if letters.startswith(c + art) and letters[len(c + art):] in _WORD_FIXES:
                return c + art, letters[len(c + art):]
    return None


def alternatives(raw: str) -> tuple[str, ...]:
    """Other imla'i folds the same Uthmani word can stand for (the rasm cannot tell them apart), besides ``search_fold(raw)``.

    A final وا whose alef is silent is written for the plural verb (قَالُوا) and also for a singular stem ending in waw
    (يَدْعُو يَتْلُو يَرْجُو): the rasm writes the alef in both, the imla'i text only in the first. A plural waw written without the
    alef after hamza (جَآءُو) is جَاءُوا in the imla'i text.
    """
    res = to_imlai(raw)
    if res is None:
        return ()
    f = arabic.folded("".join(b for b, _ in res[0]).replace(WILD, "ا"))
    alts: list[str] = []
    us = _units(raw)
    if us and us[-1].base == "ا" and (SMALL_ZERO in us[-1].marks or SUKUN in us[-1].marks) and len(f) > 3 and f.endswith("ا"):
        alts.append(f[:-1])
    if f.endswith("اءو"):
        alts.append(f + "ا")
    return tuple(alts)


def canonical(raw: str) -> str | None:
    """The fold of the word in imla'i shape, or None if it shows no Uthmani feature (the ordinary fold applies then)."""
    res = to_imlai(raw)
    return None if res is None else arabic.folded("".join(b for b, _ in res[0]).replace(WILD, "ا"))


def search_fold(raw: str) -> str:
    """The fold used to search the index: Uthmani-aware for a word with an Uthmani feature, else the ordinary fold."""
    c = canonical(raw)
    return c if c is not None else arabic.folded(raw)


def _marks_by_letter(units: list[tuple[str, str]]) -> list[tuple[str, frozenset[str]]]:
    """[(folded letter, vowel marks)] with a tanween fatha on a final alef moved to the letter before it."""
    out = [[arabic.folded(b.replace(WILD, "ا")), set(m)] for b, m in units]
    if len(out) >= 2 and out[-1][0] == "ا" and FATHATAN in out[-1][1]:
        out[-1][1].discard(FATHATAN)
        out[-2][1].add(FATHATAN)
    return [(b, frozenset(m)) for b, m in out]


def vowel_conflicts(quote_raw: str, source_raw: str) -> list[tuple[int, str]]:
    """Vowel marks (fatha, damma, kasra, tanween, shadda) the quote writes that the source word does not have at the same letter.

    Both words are compared in imla'i shape and must have the same letters; a mark the quote leaves out is not a conflict
    (a partly vocalised quotation is fine). Empty if the letters cannot be aligned.
    """
    res = to_imlai(quote_raw)
    if res is None:
        return []
    q = _marks_by_letter(res[0])
    s = _marks_by_letter([(u.base, u.vowel_marks()) for u in _units(source_raw) if u.base and u.base != TATWEEL])
    if [b for b, _ in q] != [b for b, _ in s]:
        return []
    # A shadda the source word lacks is the printed rasm's mark of idgham, not a vowel: on the first letter it assimilates the
    # sound before the word (لِّلْمُتَّقِينَ); after a letter that has no vowel it assimilates that letter (أَرَدتُّمْ).
    def idgham(i: int) -> bool:
        return i == 0 or (not q[i - 1][1] and not s[i - 1][1])

    return [(i, m) for i, ((_, qm), (_, sm)) in enumerate(zip(q, s)) for m in sorted(qm - sm) if not (m == SHADDA and idgham(i))]


def _exact(letters: str) -> str:
    """Letters compared exactly, except the spellings of one letter the rasm and the imla'i text share (ٱ = ا, ى = ي)."""
    return arabic.letters(letters).replace("ٱ", "ا").replace("ى", "ي").replace("ی", "ي")


def exact_forms(raw: str) -> list[str]:
    """The imla'i spellings (hamza seats kept: أ إ آ ئ ؤ stay what they are) the Uthmani word can be, or [] if it shows no feature.

    Only a madd sign (آ after a fatha: لَآ = لَا) and an alef the rasm writes but the imla'i text may omit give more than one.
    """
    res = to_imlai(raw)
    if res is None:
        return []
    letters = "".join(b for b, _ in res[0])
    forms = {letters.replace(WILD, "ا"), letters.replace(WILD, "آ")}
    us = _units(raw)
    if us and us[-1].base == "ا" and (SMALL_ZERO in us[-1].marks or SUKUN in us[-1].marks):
        forms |= {f[:-1] for f in forms if len(f) > 3 and f.endswith("ا")}
    if arabic.folded(letters.replace(WILD, "ا")).endswith("اءو"):
        forms |= {f + "ا" for f in forms}
    return sorted(_exact(f) for f in forms)


def explain(quote_raw: str, source_raw: str) -> tuple[str, ...] | None:
    """The conventions (see the module docstring) by which ``quote_raw`` is the Uthmani spelling of the source word, else None.

    None also when the quote word shows no Uthmani feature: ordinary spelling differences are judged by the verifier's
    existing rules, not here. The transformed letters must be *identical* to the source's, hamza seats included: أَمَنُوا is not
    ءَامَنُوا, although both fold to the same search key.
    """
    forms = exact_forms(quote_raw)
    if not forms or _exact(source_raw) not in forms:
        return None
    return tuple(sorted(to_imlai(quote_raw)[1]))


def equivalent(quote_raw: str, source_raw: str) -> bool:
    return explain(quote_raw, source_raw) is not None


_SKELETON_DROP = set("اويءىأإؤئآ")


def same_skeleton(quote_raw: str, source_raw: str) -> bool:
    """The two words have the same consonants in the same order (no rule makes them equal, so they are NOT equivalent).

    Used only to tell a spelling the rules do not cover from a different word: the verifier then says "uncertain" and offers
    no replacement, instead of calling a correct Uthmani spelling a wording error. Never makes anything "matched".
    """
    def skeleton(w: str) -> str:
        return "".join(c for c in arabic.folded(w) if c not in _SKELETON_DROP)

    a, b = skeleton(quote_raw), skeleton(source_raw)
    return len(a) >= 2 and a == b
