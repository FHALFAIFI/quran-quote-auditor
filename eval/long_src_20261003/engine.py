"""Engine for eval/build_articles_long_20261003.py.

Quran words are cut from the Quranpedia Hafs text by coordinates (the app's source object is used only to READ the text,
never its detection code). A quotation is declared with Q(surah, ayah, "plain locator words", ...): the locator is only used
to find the coordinates (the words are looked up in the surah's word stream, starting in `ayah`); the quote text itself is
the Quranpedia text cut at those coordinates, then optionally altered (sub / drop / ins = the labelled wording errors),
then optionally stripped of vowels (plain) or put into an Uthmani form (uth: hamzat-wasl alef, small sukun).
Prose is hand-written in the sibling data files; {key} in a paragraph is replaced by the rendered quotation.
"""
from __future__ import annotations

import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from app.quran_source import source  # noqa: E402  (read-only access to the text)
from app.surahs import SURAHS  # noqa: E402

idx = source.get()
COUNTS = {n: c for n, _, c in SURAHS}
MARKS = re.compile(r"[ً-ٰٟۖ-ۭـ﻿]")
FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})
OPEN = {"﴿": "﴾", "«": "»", '"': '"', "“": "”"}


def norm_words(t):
    return re.sub(r"[^ء-ي ]", " ", MARKS.sub("", t.replace("ٱ", "ا"))).translate(FOLD).split()


def strip(t):
    return MARKS.sub("", t).replace("ٱ", "ا")


# per-surah stream of (folded word, verse, raw word)
streams: dict[int, list[tuple[str, int, str]]] = {}
for (s, n), a in sorted(idx.ayahs.items()):
    for raw in a.words:
        nw = norm_words(raw)
        assert len(nw) == 1, (s, n, raw)
        streams.setdefault(s, []).append((nw[0], n, raw))
_fold_streams = {s: [w for w, _, _ in st] for s, st in streams.items()}


def occurrences(ws):
    out = []
    for s, fw in _fold_streams.items():
        for i in range(len(fw) - len(ws) + 1):
            if fw[i:i + len(ws)] == ws:
                st = streams[s]
                out.append((s, st[i][1], st[i + len(ws) - 1][1]))
    return out


def uthmani(word, override=None):
    if override:
        return override
    w = word.replace("ْ", "ۡ")
    return re.sub(r"^([وفبكل]?[َِ]?)ا(?=ل)", r"\1ٱ", w)


class Q:
    """One gold quotation. See the module docstring."""

    def __init__(self, s, a, text, *, form="plain", mark=None, ref=None, ref_kind=None, sub=None, drop=(), ins=None,
                 wasl=(), uw=None, tags=()):
        self.s, self.a, self.text, self.form, self.mark = s, a, text, form, mark
        self.ref, self.ref_kind = ref, ref_kind
        self.sub, self.drop, self.ins = dict(sub or {}), set(drop), dict(ins or {})
        self.wasl, self.uw, self.extra_tags = set(wasl), dict(uw or {}), list(tags)
        assert (ref is None) == (ref_kind is None), (s, a, text)
        assert form in ("plain", "vocal", "uth")
        ws = norm_words(text)
        st = streams[s]
        fw = _fold_streams[s]
        hits = [i for i in range(len(fw) - len(ws) + 1) if fw[i:i + len(ws)] == ws and st[i][1] == a]
        assert hits, f"locator not found at {s}:{a}: {text}"
        i = hits[0]
        self.raw = [st[k][2] for k in range(i, i + len(ws))]
        self.cw = ws
        self.ayah_start, self.ayah_end = st[i][1], st[i + len(ws) - 1][1]
        self.correct_text = strip(" ".join(self.raw))

    def quote(self):
        ws = list(self.raw)
        for i, new in self.sub.items():
            ws[i] = new
        out = []
        for i in range(len(ws) + 1):
            if i in self.ins:
                out.append(self.ins[i])
            if i < len(ws) and i not in self.drop:
                out.append(ws[i])
        if self.form == "uth":
            out = [self.uw.get(k) or uthmani(w) for k, w in enumerate(out)]
            out = [re.sub(r"^([وفبكل]?[َِ]?)ا", r"\1ٱ", w) if k in self.wasl else w for k, w in enumerate(out)]
        t = " ".join(out)
        return strip(t) if self.form == "plain" else t

    def render(self):
        q = self.quote()
        return f"{self.mark}{q}{OPEN[self.mark]}" if self.mark else q


def derived_tags(q: Q, quote: str, wording: str):
    """Same derivations as the validator (re-implemented here so that the builder writes the tags it will be checked on)."""
    t = set()
    qw, cw = norm_words(quote), q.cw
    ops = [o for o in SequenceMatcher(None, qw, cw, autojunk=False).get_opcodes() if o[0] != "equal"]
    if wording != "correct":
        t.add("wording_error")
        if len(ops) == 1:
            op = ops[0]
            if op[0] == "delete" and op[4] - op[3] == 0 and op[2] - op[1] == 1 or (op[0] == "insert" and op[4] - op[3] == 1):
                t.add("missing_word" if op[0] == "insert" else "extra_word")
            if op[0] == "replace" and op[2] - op[1] == 1 and op[4] - op[3] == 1:
                t.add("one_word_wrong")
        for op in ops:
            if op[3] == 0:
                t.add("wrong_first_word")
            if op[4] == len(cw):
                t.add("wrong_last_word")
    if "ٱ" in quote or re.search("[ۖ-ۭ]", quote):
        t.add("uthmani")
    elif re.search("[ً-ْٰ]", quote):
        t.add("vocalized")
    else:
        t.add("plain")
    t.add("multi_verse" if q.ayah_end > q.ayah_start else "single_verse")
    full = []
    for n in range(q.ayah_start, q.ayah_end + 1):
        full += norm_words(" ".join(idx.ayahs[(q.s, n)].words))
    if cw == full:
        t.add("full_verse")
    else:
        t.add("partial")
        st = [k for k in range(len(full) - len(cw) + 1) if full[k:k + len(cw)] == cw]
        if st and st[0] + len(cw) < len(full):
            t.add("incomplete")
    if len(cw) <= 4:
        t.add("short")
    return t


def build_case(mod):
    """mod: a data module with ID, CATEGORY, PARAS (list[str]), QUOTES (dict key -> Q), NEGATIVES, FORMULAS."""
    quotes: dict[str, Q] = mod.QUOTES
    used = set()

    def sub(m):
        k = m.group(1)
        used.add(k)
        return quotes[k].render()

    paras = [re.sub(r"\{(\w+)\}", sub, p) for p in mod.PARAS]
    art = "\n\n".join(paras)
    assert used == set(quotes), (mod.ID, set(quotes) - used)
    gold = []
    missing = []
    places = []
    for k, q in quotes.items():
        places.append((q.s, q.ayah_start, q.ayah_end))
    for k, q in quotes.items():
        quote = q.quote()
        assert art.count(quote) == 1, (mod.ID, k, art.count(quote), quote)
        locs = occurrences(q.cw)
        assert (q.s, q.ayah_start, q.ayah_end) in locs, (mod.ID, k, locs)
        wording = "wording_error" if (q.sub or q.drop or q.ins) else "correct"
        tags = derived_tags(q, quote, wording)
        tags.add("marked" if q.mark else "unmarked")
        if len(locs) > 1:
            tags.add("repeated_in_quran")
        p = art.index(quote)
        q_end = p + len(quote)
        rt = q.ref
        reference = q.ref_kind or "missing"
        if rt is None:
            tags.add("no_reference")
        else:
            if art.count(rt) < 1:
                missing.append((k, rt))
                continue
            if re.search(r"[٠-٩]", rt):
                tags.add("arabic_indic_digits")
            if re.match(r"^\s*[\d٠-٩]", rt):
                tags.add("numeric_ref")
            if re.search(r"[\d٠-٩]\s*[-–]\s*[\d٠-٩]", rt):
                tags.add("range_ref")
            if re.search(r"سورة|الآية|الآيات|آية", rt):
                tags.add("long_form_ref")
            if reference == "incorrect":
                tags.add("wrong_reference")
            after = [m.start() for m in re.finditer(re.escape(rt), art) if m.start() >= q_end]
            bef = [m.start() for m in re.finditer(re.escape(rt), art) if m.end() <= p]
            if any(a - q_end <= 160 and "\n\n" not in art[q_end:a] for a in after):
                tags.add("inline_ref")
            if any(p - (b + len(rt)) <= 160 and "\n\n" not in art[b:p] for b in bef):
                tags.add("ref_before")
            if any("\n\n" in art[q_end:a] for a in after):
                tags.add("footnote_ref")
        same = sum(1 for pl in places if pl[0] == q.s and pl[1] <= q.ayah_end and q.ayah_start <= pl[2])
        if same >= 2:
            tags.add("repeated")
        tags.add("long_article")
        tags.update(q.extra_tags)
        gold.append({
            "quote": quote, "surah": q.s, "ayah_start": q.ayah_start, "ayah_end": q.ayah_end,
            "correct_text": q.correct_text, "wording": wording, "ambiguous": len(locs) > 1,
            "reference_text": rt, "reference": reference, "unmarked": not q.mark, "tags": sorted(tags),
        })
    assert not missing, (mod.ID, 'reference text not in article', missing)
    for n in list(mod.NEGATIVES) + list(mod.FORMULAS):
        assert n in art, (mod.ID, n)
    return {"id": mod.ID, "category": mod.CATEGORY, "article": art, "gold": gold,
            "negatives": list(mod.NEGATIVES), "formulas": list(mod.FORMULAS)}
