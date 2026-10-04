"""Builds the diagnostic HARD-QUOTATIONS sets of 4 Oct 2026 (challenge period):

    eval/hard_quotes_dev_20261004.json       development / diagnostic split (used to diagnose and tune the detector)
    eval/hard_quotes_heldout_20261004.json   held-out split (meant to be run ONCE, after tuning)

    .venv/bin/python eval/build_hard_quotes_20261004.py [--freeze]      # run from the repo root

Assistant-authored development data (an AI subagent, Claude, in a fresh context, 4 Oct 2026); NOT human-reviewed, NOT
independent. The prose of every case is hand-written in eval/hard_quotes_src_20261004/dev.py and heldout.py. Quran words
are never typed by hand: each quotation is declared by COORDINATES, Q(surah, ayah, word_start, word_end, "check"), where
word_end is exclusive (for a multi-ayah quotation, word_start counts in ayah and word_end in a_end), and the words are cut
from the cached Quranpedia Hafs text (the JSON file the app caches, read directly here; no Quran text is stored in Git
except these short quotations). "check" is the plain spelling of the words at those coordinates and only guards against a
wrong coordinate. The cut words are then perturbed by explicit, recorded edits (sub={position: written word},
omit={positions}, ins={position: inserted word}; positions count in the quoted range, 0-based, before any edit), and
rendered in one of three script forms: plain (diacritics removed), vocal (the Quranpedia diacritics kept) or uth (an
Uthmani-style rendering of the same words: hamzat al-wasl written ٱ and the sukun written as the Quranic small high
dotless head ۡ, as in eval/long_src_20261003/engine.py; NOT a full Uthmani rasm).

The detector was NOT consulted: the author did not open app/audit.py, phrases.py, verifier.py, suggest.py, corrections.py,
uthmani.py, app/extraction/*, app/static/*.js, tests/, docs/EVALUATION.md or docs/TEST_LOG.md, did not start the server,
and did not call any app function that detects or verifies. Labels follow from the Quranpedia text and from the rules
written in this file and checked by eval/validate_hard_quotes_20261004.py (which uses its own normalisation).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from app.surahs import SURAHS  # noqa: E402  (names and verse counts only; no Quran text)

SOURCE = Path(os.environ.get("HQ_SOURCE", Path(tempfile.gettempdir()) / "quran-auditor-cache" / "hafs-mushaf-1.json"))

# ---------------------------------------------------------------- normalisation (builder side)
_MARKS = re.compile("[ً-ٰٟۖ-ۭـ﻿]")
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})


def fold_words(t: str) -> list[str]:
    return [w for w in re.sub("[^ء-ي ]", " ", _MARKS.sub("", t).translate(_FOLD)).split() if w]


def strip_marks(t: str) -> str:
    return _MARKS.sub("", t).replace("ٱ", "ا")


# ---------------------------------------------------------------- source
_data = json.loads(SOURCE.read_text(encoding="utf-8"))
AYAH: dict[tuple[int, int], list[str]] = {}
for _a in _data["ayahs"]:
    AYAH[(_a["surah"], _a["number"])] = [w for w in _a["text"].replace("﻿", "").split() if fold_words(w)]
STREAM: list[tuple[str, int, int, int]] = []  # (folded word, surah, ayah, index in ayah)
for (_s, _n), _ws in sorted(AYAH.items()):
    for _i, _w in enumerate(_ws):
        STREAM.append((fold_words(_w)[0], _s, _n, _i))
_FIRST: dict[str, list[int]] = {}
for _k, _t in enumerate(STREAM):
    _FIRST.setdefault(_t[0], []).append(_k)
NAME = {n: name for n, name, _ in SURAHS}


def occurrences(ws: list[str]) -> list[tuple[int, int, int]]:
    """(surah, first ayah, last ayah) of every contiguous occurrence of the folded words ws (never across surahs)."""
    out = []
    for k in _FIRST.get(ws[0], []) if ws else []:
        seg = STREAM[k:k + len(ws)]
        if len(seg) == len(ws) and [t[0] for t in seg] == ws and seg[0][1] == seg[-1][1]:
            out.append((seg[0][1], seg[0][2], seg[-1][2]))
    return out


def longest_run(text: str) -> str | None:
    """The longest run (>= 3 folded words) of `text` that occurs in the Quran, or None."""
    ws = fold_words(text)
    best = None
    for i in range(len(ws)):
        for j in range(len(ws), i + 2, -1):
            if (best is None or j - i > len(best.split())) and occurrences(ws[i:j]):
                best = " ".join(ws[i:j])
                break
    return best


# ---------------------------------------------------------------- declarations
LEAD_INS = ["قال الله تعالى", "قال تعالى", "يقول الله عز وجل", "يقول الله تعالى", "في القرآن الكريم", "كما في قوله تعالى",
            "قوله تعالى", "قال سبحانه", "يقول سبحانه", "جاء في التنزيل", "في كتاب الله", "قول الحق سبحانه"]
CLOSE = {"﴿": "﴾", "«": "»", '"': '"'}


def uth_word(w: str, wasl: bool) -> str:
    w = w.replace("ْ", "ۡ")
    w = re.sub(r"^([وفبكل]?[َِ]?)ا(?=ل)", "\\1ٱ", w)
    if wasl:
        w = re.sub(r"^([وف]?[َ]?)ا", "\\1ٱ", w)
    return w


class Q:
    def __init__(self, s, a, w0, w1, check, *, a_end=None, form="plain", mark=None, sub=None, omit=(), ins=None,
                 ref=None, refk=None, lead=None, foot=False, wasl=()):
        assert form in ("plain", "vocal", "uth") and mark in (None, "﴿", "«", '"')
        assert (ref is None) == (refk is None)
        self.s, self.a, self.a_end, self.w0, self.w1 = s, a, a_end or a, w0, w1
        self.form, self.mark, self.ref, self.refk, self.lead, self.foot = form, mark, ref, refk, lead, foot
        self.sub, self.omit, self.ins, self.wasl = dict(sub or {}), sorted(omit), dict(ins or {}), set(wasl)
        if self.a_end == a:
            raw = AYAH[(s, a)][w0:w1]
        else:
            raw = AYAH[(s, a)][w0:]
            for n in range(a + 1, self.a_end):
                raw += AYAH[(s, n)]
            raw += AYAH[(s, self.a_end)][:w1]
        self.raw = raw
        got = fold_words(" ".join(raw))
        assert got == fold_words(check), f"{s}:{a} [{w0}:{w1}] is «{' '.join(got)}», not «{check}»"
        self.correct_text = strip_marks(" ".join(raw))
        self.cw = got

    def words(self):
        out = []
        n = len(self.raw)
        for i in range(n + 1):
            if i in self.ins:
                out.append(self.ins[i])
            if i < n and i not in self.omit:
                out.append(self.sub.get(i, self.raw[i]))
        return out

    def quote(self) -> str:
        ws = self.words()
        if self.form == "plain":
            return strip_marks(" ".join(ws))
        if self.form == "uth":
            ws = [uth_word(w, k in self.wasl) for k, w in enumerate(ws)]
        return " ".join(ws).replace("﻿", "")

    def render(self) -> str:
        q = self.quote()
        return f"{self.mark}{q}{CLOSE[self.mark]}" if self.mark else q

    def error(self):
        n = len(self.raw)
        ops = [("substitute", p) for p in self.sub] + [("omit", p) for p in self.omit] + [("insert", p) for p in self.ins]
        if not ops:
            return "none", None
        details = []
        for op, p in sorted(ops, key=lambda x: (x[1], x[0])):
            src = strip_marks(self.raw[p]) if op != "insert" else None
            written = None if op == "omit" else (self.sub[p] if op == "substitute" else self.ins[p])
            if written is not None and self.form == "uth":
                written = uth_word(written, False)
            elif written is not None and self.form == "plain":
                written = strip_marks(written)
            details.append({"op": op, "position": p, "written": written, "source": src})
        if len(ops) == 2:
            return "two_errors", details
        assert len(ops) == 1, "at most two edits per quotation"
        op, p = ops[0]
        if op == "substitute":
            kind = "wrong_first" if p == 0 else "wrong_last" if p == n - 1 else "substitution"
        elif op == "omit":
            assert 0 < p < n - 1, "omission is declared in the middle"
            kind = "omission"
        else:
            kind = "extra_word"
        return kind, details[0]


class N:
    def __init__(self, text, kind):
        assert kind in ("prose_lookalike", "hadith", "dua", "proverb", "common_phrase", "hard_negative"), kind
        self.text, self.kind = text, kind


class C:
    def __init__(self, cid, category, text, quotes=None, negs=(), formulas=()):
        self.cid, self.category, self.text = cid, category, text
        self.quotes = dict(quotes or {})
        self.negs, self.formulas = list(negs), list(formulas)


# ---------------------------------------------------------------- rules for "expect"
def expect_for(n_words: int, ambiguous: bool, wording: str, marked: bool, lead: bool, refk: str) -> dict:
    referenced = refk != "missing"
    detect = "required" if (marked or lead or referenced or (n_words >= 4 and not ambiguous)) else "desirable"
    max_wording = "matched" if wording == "correct" else "difference"
    ayah_ref_ok = refk == "correct"
    allowed = marked and (ayah_ref_ok or (lead and n_words >= 6 and not ambiguous))
    return {"detect": detect, "max_wording": max_wording,
            "auto_replacement": "allowed_if_span_and_verse_established" if allowed else "forbidden",
            "gold_verse_listed": True}


def build_case(c: C) -> dict:
    used = set()

    def put(m):
        used.add(m.group(1))
        return c.quotes[m.group(1)].render()

    art = re.sub(r"\{(\w+)\}", put, c.text)
    assert used == set(c.quotes), (c.cid, set(c.quotes) - used)
    assert art == art.strip() and "\n\n\n" not in art, c.cid
    gold = []
    places = [(q.s, q.a, q.a_end) for q in c.quotes.values()]
    for key, q in c.quotes.items():
        quote = q.quote()
        assert art.count(quote) == 1, (c.cid, key, art.count(quote))
        start = art.index(quote)
        end = start + len(quote)
        locs = occurrences(q.cw)
        assert (q.s, q.a, q.a_end) in locs, (c.cid, key, locs)
        error, detail = q.error()
        wording = "correct" if error == "none" else "wording_error"
        qw = fold_words(quote)
        if wording == "correct":
            assert qw == q.cw, (c.cid, key)
        else:
            assert qw != q.cw and not occurrences(qw), (c.cid, key, "misquote must differ and not be Quran text")
        full = []
        for n in range(q.a, q.a_end + 1):
            full += fold_words(" ".join(AYAH[(q.s, n)]))
        partial = q.cw != full
        refk = q.refk or "missing"
        context = []
        lead_text = None
        if q.lead:
            assert q.lead in LEAD_INS or any(l in q.lead for l in LEAD_INS), (c.cid, q.lead)
            o = start - (1 if q.mark else 0)
            window = art[max(0, o - 40):o]
            assert q.lead in window, (c.cid, key, "lead-in must end within 40 characters before the quotation")
            lead_text = q.lead
            context.append("lead_in")
        if refk in ("correct", "incorrect", "out_of_range"):
            context.append("reference_ayah")
        if refk == "surah_only":
            context.append("reference_surah")
        if q.ref is not None:
            assert q.ref in art, (c.cid, key, q.ref)
        if q.foot:
            after = art.find(q.ref, end)
            assert after > 0 and "\n" in art[end:after], (c.cid, key, "footnote reference must sit after a line break")
            context.append("footnote_ref")
        if q.mark == "﴿":
            context.append("brackets")
        elif q.mark:
            context.append("quotation_marks")
        if q.form == "uth":
            context.append("uthmani")
        if not context:
            context = ["none"]
        tags = set()
        tags.add("marked" if q.mark else "unmarked")
        tags.add({"plain": "plain", "vocal": "vocalized", "uth": "uthmani"}[q.form])
        tags.add("multi_verse" if q.a_end > q.a else "single_verse")
        tags.add("partial" if partial else "full_verse")
        if len(q.cw) <= 3:
            tags.add("short")
        if wording != "correct":
            tags.add("wording_error")
            tags.add({"substitution": "one_word_wrong", "omission": "missing_word", "extra_word": "extra_word",
                      "wrong_first": "wrong_first_word", "wrong_last": "wrong_last_word", "two_errors": "two_edits"}[error])
        tags.add({"missing": "no_reference", "correct": "reference_correct", "incorrect": "wrong_reference",
                  "out_of_range": "out_of_range_reference", "surah_only": "surah_only_reference"}[refk])
        if len(locs) > 1:
            tags.add("repeated_in_quran")
        if sum(1 for p in places if p[0] == q.s and p[1] <= q.a_end and q.a <= p[2]) >= 2:
            tags.add("repeated_in_article")
        if lead_text:
            tags.add("lead_in")
        if q.foot:
            tags.add("footnote_ref")
        gold.append({
            "quote": quote, "surah": q.s, "ayah_start": q.a, "ayah_end": q.a_end,
            "word_start": q.w0, "word_end": q.w1, "correct_text": q.correct_text,
            "wording": wording, "error": error, "error_detail": detail,
            "ambiguous": len(locs) > 1, "reference_text": q.ref, "reference": refk,
            "unmarked": not q.mark, "partial": partial, "context": context, "lead_in_text": lead_text,
            "start": start, "end": end,
            "expect": expect_for(len(q.cw), len(locs) > 1, wording, bool(q.mark), bool(lead_text), refk),
            "tags": sorted(tags),
        })
    gold.sort(key=lambda g: g["start"])
    negs = []
    for n in c.negs:
        assert art.count(n.text) >= 1, (c.cid, n.text)
        s0 = art.index(n.text)
        run = longest_run(n.text)
        if n.kind == "hard_negative":
            assert run, (c.cid, n.text, "a hard negative must share a run of 3+ words with the Quran")
        else:
            assert run is None, (c.cid, n.text, run)
        assert not any(s0 < g["end"] and g["start"] < s0 + len(n.text) for g in gold), (c.cid, n.text)
        negs.append({"text": n.text, "start": s0, "end": s0 + len(n.text), "kind": n.kind, "shares_quran_run": run,
                     "expect": "no_finding_or_possible_only"})
    for f in c.formulas:
        assert f in art and occurrences(fold_words(f)), (c.cid, f)
    return {"id": c.cid, "category": c.category, "article": art, "gold": gold,
            "negatives": [n["text"] for n in negs], "negatives_detail": negs, "formulas": list(c.formulas)}


ABOUT = (
    "Diagnostic evaluation set of HARD Quran quotations in Arabic prose, {split} split, v1 (4 Oct 2026, challenge period). "
    "ASSISTANT-AUTHORED DEVELOPMENT DATA: every article and every label was written on 4 Oct 2026 by an AI subagent (Claude) "
    "working in a fresh context; it is NOT human-reviewed and NOT independent (the same assistant wrote the texts and the labels, "
    "so the cases favour wordings it finds natural and the scores measure agreement with this author, not accuracy on real writers). "
    "PURPOSE: the dev split (hard_quotes_dev_20261004.json) will be used to diagnose and tune the detector; the held-out split "
    "(hard_quotes_heldout_20261004.json) is meant to be run ONCE, after tuning, and any later rerun after a further change must say "
    "that it is no longer held out. Both files are frozen by SHA-256 (eval/hard_quotes_<split>_20261004.sha256). "
    "WHAT THE AUTHOR READ: the existing eval/*.json sets (only to copy the schema and to avoid their gold ayahs, quotations and "
    "negatives), eval/validate_articles_long_20261003.py, eval/long_src_20261003/engine.py, eval/build_articles_long_20261003.py, "
    "the label functions expected_reference / expected_wording at the top of eval/run_eval.py, app/surahs.py (names and verse "
    "counts) and the cached Quranpedia Hafs JSON. WHAT THE AUTHOR DID NOT READ OR RUN: app/audit.py, app/phrases.py, "
    "app/verifier.py, app/suggest.py, app/corrections.py, app/uthmani.py, app/extraction/*, app/static/*.js, tests/, "
    "docs/EVALUATION.md, docs/TEST_LOG.md; the server was not started and no app detection or verification function was called. "
    "HOW IT IS MADE: eval/build_hard_quotes_20261004.py composes each case from hand-written prose "
    "(eval/hard_quotes_src_20261004/{split}.py) and Quran words cut from the cached Quranpedia Hafs text by coordinates "
    "(surah, ayah, word range), then applies explicit recorded edits; eval/validate_hard_quotes_20261004.py re-checks every label "
    "against the same source with its own normalisation and prints 'labels OK'. Prose passages were reworded where the validator "
    "listed an unlabelled run of three or more words that occurs in the Quran (such runs are either removed or labelled as hard "
    "negatives); this is not tuning to any detector. "
    "SCHEMA: same fields as eval/articles_long_20261003.json, so eval/run_eval.py can score it (id, category, article, gold, "
    "negatives = plain strings, formulas), plus: negatives_detail = [{{text, start, end, kind = prose_lookalike | hadith | dua | "
    "proverb | common_phrase | hard_negative, shares_quran_run = the longest folded run of 3+ words it shares with the Quran or null, "
    "expect = no_finding_or_possible_only}}]; each gold item additionally has start/end (code-point offsets of quote in article), "
    "word_start/word_end (0-based, word_end exclusive, counted in the Quranpedia words of ayah_start / ayah_end), "
    "error = none | substitution | omission | wrong_first | wrong_last | extra_word | two_errors, error_detail (one edit "
    "{{op = substitute | omit | insert, position (0-based in the correct words, before any edit), written (as in the quote; null for an "
    "omission), source (plain Quranpedia word; null for an insertion)}}, a list of two such edits for two_errors, null for none), "
    "context (none | lead_in | reference_ayah | reference_surah | quotation_marks | brackets | uthmani | footnote_ref), lead_in_text, "
    "partial (less than the whole verse or verse range), and expect = {{detect: required (marked, lead-in, any reference, or 4+ words "
    "and not ambiguous) | desirable (2-3 words unmarked, or an ambiguous unmarked phrase without lead-in or reference); max_wording: "
    "difference for every misquotation (never matched) | matched for a correct quotation; auto_replacement: "
    "allowed_if_span_and_verse_established only when the quotation is marked (brackets or quotation marks) AND either the written "
    "reference names the right ayah or a lead-in introduces a quotation of 6+ words that is not ambiguous, otherwise forbidden (no "
    "replacement text may be proposed before the writer confirms); gold_verse_listed: true}}. wording uses the existing values "
    "correct | wording_error. Uthmani-script quotations (context uthmani) are an Uthmani-style rendering of the Quranpedia words "
    "(hamzat al-wasl as ٱ, sukun as ۡ), not a full Uthmani rasm; no new Quran text file was added. Gold ayahs of the two splits are "
    "disjoint from each other and from the gold ayahs of eval/cases.json, heldout.json, phrases_frozen.json, articles_frozen.json and "
    "articles_long_20261003.json, and no correct_text equals one of theirs. Every gold quote occurs exactly once in its article "
    "(run_eval.py locates quotations by text), so a quotation that a long article uses twice is written once vocalized or marked "
    "and once plain. Hadith, du'a and proverb negatives were written from the author's memory and were NOT checked against hadith "
    "collections; they are labelled only as not being Quran text (a negative of kind hard_negative shares a Quran run, recorded in "
    "shares_quran_run, and is expected to give no finding or a 'possible' finding only). Wording errors are the author's guesses at "
    "realistic slips, not a sample of real writers' errors. {counts}"
)


def counts_line(cases: list[dict]) -> str:
    from collections import Counter
    short = [c for c in cases if c["category"] != "long_article"]
    longs = [c for c in cases if c["category"] == "long_article"]
    gold = [g for c in cases for g in c["gold"]]
    err = Counter(g["error"] for g in gold)
    negk = Counter(n["kind"] for c in cases for n in c["negatives_detail"])
    return (f"Contents: {len(cases)} cases ({len(short)} short articles, {len(longs)} long articles), {len(gold)} gold quotations "
            f"({sum(len(c['gold']) for c in short)} in short articles), errors {dict(sorted(err.items()))}, "
            f"{sum(negk.values())} negatives {dict(sorted(negk.items()))}, "
            f"{sum(len(c['formulas']) for c in cases)} formulas.")


def main() -> int:
    sys.modules.setdefault("build_hard_quotes_20261004", sys.modules[__name__])
    from hard_quotes_src_20261004 import dev, heldout
    for split, mod in (("dev", dev), ("heldout", heldout)):
        cases = [build_case(c) for c in mod.CASES]
        ids = [c["id"] for c in cases]
        assert len(set(ids)) == len(ids), "duplicate ids"
        about = ABOUT.format(split=split, counts=counts_line(cases))
        out = HERE / f"hard_quotes_{split}_20261004.json"
        text = json.dumps({"_about": about, "version": f"hard-quotes-{split}-20261004", "cases": cases},
                          ensure_ascii=False, indent=1) + "\n"
        out.write_text(text, encoding="utf-8")
        print(out.name, len(cases), "cases,", sum(len(c["gold"]) for c in cases), "gold,",
              sum(len(c["negatives"]) for c in cases), "negatives")
        if "--freeze" in sys.argv:
            digest = hashlib.sha256(out.read_bytes()).hexdigest()
            (HERE / f"hard_quotes_{split}_20261004.sha256").write_text(f"{digest}  {out.name}\n", encoding="utf-8")
            print("frozen:", digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
