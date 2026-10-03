"""Builds eval/suggest_cases_20261003.json: a frozen evaluation set for POST /api/suggest (verse suggestions while the
writer types), written 2026-10-03 by an unknown author; blindness to the implementation NOT verified (see _about).

Quran words are NEVER typed from memory here: every Quran string in a `before` text is cut from the Quranpedia Hafs text
(the app's source object is used only to read the text, never its matching code) by coordinates
(surah, ayah, first word, last word) and, for the wrong-word / missing-word / partial-word cases, by an explicit edit applied
to those words. The Arabic prose around the Quran words is written by hand. The builder asserts every property it relies on
(unique places, ambiguity, non-existence of the typed variants) by searching the folded word stream; the independent
validator (eval/validate_suggest_cases.py) re-checks all of it with its own code.

    .venv/bin/python eval/build_suggest_cases.py            # writes eval/suggest_cases_20261003.json
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.quran_source import source  # noqa: E402  (only used to read the Quran text)

idx = source.get()
OUT = ROOT / "eval" / "suggest_cases_20261003.json"

MARKS = re.compile(r"[ً-ٰٟۖ-ۭـ﻿]")
FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})


def fold_words(t: str) -> list[str]:
    """Folded words of typed text: Uthmani 'waw + dagger alef' is an alef, alef-wasla is an alef, marks are dropped."""
    t = re.sub("و[ً-ٟ]*ٰ", "ا", t)
    return re.sub(r"[^ء-ي ]", " ", MARKS.sub("", t).translate(FOLD)).split()


def strip(t: str) -> str:
    return MARKS.sub("", t)


def W(s: int, a: int) -> list[str]:
    return idx.ayahs[(s, a)].words


# per-surah folded word streams: (folded word, ayah, index of the word in its ayah)
streams: dict[int, list[tuple[str, int, int]]] = {}
for (_s, _n), _a in sorted(idx.ayahs.items()):
    for _i, _w in enumerate(_a.words):
        fw = fold_words(_w)
        assert len(fw) == 1, (_s, _n, _w, fw)
        streams.setdefault(_s, []).append((fw[0], _n, _i))
STREAM_WORDS = {s: [x[0] for x in st] for s, st in streams.items()}


def occurrences(ws: list[str], last_prefix: str | None = None) -> list[tuple[int, int, int]]:
    """Places (surah, first ayah, last ayah) where the folded words occur contiguously; with last_prefix the final
    position only has to START with that string."""
    out = []
    n = len(ws)
    for s, fw in STREAM_WORDS.items():
        st = streams[s]
        for i in range(len(fw) - n + 1):
            if fw[i:i + n - (1 if last_prefix is not None else 0)] != ws[:n - (1 if last_prefix is not None else 0)]:
                continue
            if last_prefix is not None and not fw[i + n - 1].startswith(last_prefix):
                continue
            out.append((s, st[i][1], st[i + n - 1][1]))
    return out


# --------------------------------------------------------------------------------------------- typing styles
UTH = [("صَّلَاة", "صَّلَوٰة"), ("زَّكَاة", "زَّكَوٰة"), ("حَيَاة", "حَيَوٰة"), ("رَّحْمَٰن", "رَّحْمَـٰن"), ("هَٰذ", "هَـٰذ")]
WASLA_ARTICLE = re.compile("^(?:[وف]َ|بِ|كَ)?ا(?=ل(?:ْ|[َّ]{1,2})?[ء-ي])")
WASLA_VERB = re.compile("^ا(?=[ء-ي]ْ)")


def style_word(w: str, sty: str) -> str:
    if sty == "dia":
        return w
    if sty == "plain":
        return strip(w)
    if sty == "uth":  # Uthmani-script spelling as copied from a Quran app (alef-wasla, waw+dagger-alef, tatweel+dagger-alef)
        for a, b in UTH:
            w = w.replace(a, b)
        m = WASLA_ARTICLE.match(w) or WASLA_VERB.match(w)
        if m:
            i = m.end() - 1
            w = w[:i] + "ٱ" + w[i + 1:]
        return w
    raise ValueError(sty)


# --------------------------------------------------------------------------------------------- Quran slice specs
def _base(s, a, w0, w1, sty):
    return {"surah": s, "ayah": a, "word_from": w0, "word_to": w1, "style": sty, "edit": None}


def _wrap(ts, words, trail, gold, kind, certainty, places, **extra):
    return {"ts": ts, "typed": " ".join(words) + trail, "gold_words": gold, "kind": kind, "certainty": certainty,
            "places": places, **extra}


def cont(s, a, n, w0=0, sty="dia", nxt=2, trail=" "):
    """The writer typed words [w0, w0+n) of the ayah; the proposal is what follows."""
    ws = W(s, a)
    w1 = w0 + n
    assert w1 < len(ws), (s, a, "no word left to propose")
    pref = [fold_words(x)[0] for x in ws[w0:w1]]
    places = occurrences(pref)
    assert places == [(s, a, a)], ("continuation prefix is not unique", s, a, n, places)
    return _wrap(_base(s, a, w0, w1, sty), [style_word(x, sty) for x in ws[w0:w1]], trail, [s, a, w1, min(w1 + nxt, len(ws))],
                 ["continue"], "exact", [(s, a, a)])


def full(s, a, sty="dia", trail=""):
    """A whole ayah typed; nothing is left to add."""
    ws = W(s, a)
    pref = [fold_words(x)[0] for x in ws]
    places = occurrences(pref)
    assert places == [(s, a, a)], ("complete verse sequence is not unique", s, a, places)
    return _wrap(_base(s, a, 0, len(ws), sty), [style_word(x, sty) for x in ws], trail, None, [], None, [(s, a, a)])


def part(s, a, n, chars, w0=0, sty="dia"):
    """n whole words, then the first `chars` letters of the next word (the caret is inside that word)."""
    ws = W(s, a)
    i = w0 + n
    word = strip(ws[i])
    assert 2 <= chars < len(word) and fold_words(word)[0].startswith(fold_words(word[:chars])[0]), (s, a, i, word, chars)
    partial = word[:chars]
    pf = fold_words(partial)
    assert len(pf) == 1
    pref = [fold_words(x)[0] for x in ws[w0:i]]
    places = occurrences(pref + [pf[0]], last_prefix=pf[0])
    assert places == [(s, a, a)], ("partial-word prefix is not unique", s, a, n, places)
    ts = _base(s, a, w0, i, sty)
    ts["edit"] = {"type": "partial", "word_index": i, "letters": chars}
    return _wrap(ts, [style_word(x, sty) for x in ws[w0:i]] + [partial], "", [s, a, i, i + 1], ["complete_word"], "exact", [(s, a, a)])


def wrong(s, a, n, bad, w0=0, sty="dia"):
    """n correct words, then a wrong word (and a space): the proposal replaces it with the verse word."""
    ws = W(s, a)
    i = w0 + n
    pref = [fold_words(x)[0] for x in ws[w0:i]]
    assert n >= 3 and occurrences(pref) == [(s, a, a)], ("replace prefix not distinctive", s, a, n, occurrences(pref))
    fb, fc = fold_words(bad), fold_words(ws[i])
    assert len(fb) == 1 and fb[0] != fc[0] and not fc[0].startswith(fb[0]) and not fb[0].startswith(fc[0]), (s, a, bad, ws[i])
    assert not occurrences(pref + fb), ("the wrong word is a real continuation somewhere", s, a, bad)
    ts = _base(s, a, w0, i, sty)
    ts["edit"] = {"type": "replace", "word_index": i, "wrong": bad}
    return _wrap(ts, [style_word(x, sty) for x in ws[w0:i]] + [bad], " ", [s, a, i, i + 1], ["replace"], "probable", [(s, a, a)],
                 wrong_word=bad, correct_word=strip(ws[i]))


def miss(s, a, n, skip, w0=0, sty="dia"):
    """n correct words, then the verse word after `skip` omitted words (and a space): the proposal inserts the omitted words."""
    ws = W(s, a)
    i = w0 + n
    assert i + skip < len(ws)
    pref = [fold_words(x)[0] for x in ws[w0:i]]
    assert n >= 3 and occurrences(pref) == [(s, a, a)], ("insert prefix not distinctive", s, a, n, occurrences(pref))
    typed_last = fold_words(ws[i + skip])
    assert not occurrences(pref + typed_last), ("typed words exist as written", s, a)
    ts = _base(s, a, w0, i, sty)
    ts["edit"] = {"type": "skip", "word_index": i, "count": skip}
    return _wrap(ts, [style_word(x, sty) for x in ws[w0:i]] + [style_word(ws[i + skip], sty)], " ", [s, a, i, i + skip], ["insert"], "probable",
                 [(s, a, a)], skipped=[strip(x) for x in ws[i:i + skip]])


def amb(s, a, n, expect_places, w0=0, sty="dia", nxt=2):
    """An opening shared by several verses; expect_places must be EXACTLY the places where the typed words occur."""
    ws = W(s, a)
    w1 = w0 + n
    pref = [fold_words(x)[0] for x in ws[w0:w1]]
    places = occurrences(pref)
    assert sorted(places) == sorted(expect_places), ("ambiguity places differ", s, a, n, places)
    assert len(places) > 1
    by_place = {}
    for (ps, pa, pb) in places:
        assert pa == pb
        pws = W(ps, pa)
        # word index of the occurrence inside its own ayah
        starts = [k for k in range(len(pws) - n + 1) if [fold_words(x)[0] for x in pws[k:k + n]] == pref]
        assert len(starts) == 1, (ps, pa, starts)
        k = starts[0] + n
        assert k < len(pws), ("an occurrence ends its ayah", ps, pa)
        by_place[f"{ps}:{pa}"] = [ps, pa, k, min(k + nxt, len(pws))]
    nexts = {fold_words(W(p[0], p[1])[by_place[f'{p[0]}:{p[1]}'][2]])[0] for p in places}
    sp = _wrap(_base(s, a, w0, w1, sty), [style_word(x, sty) for x in ws[w0:w1]], " ", None, ["continue"], "exact", sorted(places),
               gold_words_by_place=by_place, distinct_continuations=len(nexts))
    return sp


def slice_(s, a, w0, w1, sty="plain", trail=" "):
    """A Quran-looking stretch used in a negative case (no gold)."""
    ws = W(s, a)
    pref = [fold_words(x)[0] for x in ws[w0:w1]]
    places = occurrences(pref)
    assert places, (s, a)
    return _wrap(_base(s, a, w0, w1, sty), [style_word(x, sty) for x in ws[w0:w1]], trail, None, [], None, sorted(places))


CASES: list[dict] = []


def ts_out(sp, role):
    return {**sp["ts"], "role": role}


def add(category, sp, *, pre="", cue=None, sep=": ", opener="", after="", close="", tail="", tail_sp=None, explicit=False, distinct=False,
        outcome=None, note, ok_status=("none",), none_acceptable=False, must_be_ambiguous=False, identical_continuation=False,
        cue_kind=None, no_ts=False):
    """Compose a case. before = pre + cue + sep + opener + typed [+ close + tail (+ tail Quran-looking words)]."""
    parts = [pre]
    if cue:
        parts.append(cue + sep)
    parts.append(opener)
    before_head = "".join(parts)
    typed = sp["typed"] if sp else ""
    before = before_head + typed + close + tail + (tail_sp["typed"] if tail_sp else "")
    assert len(before) <= 800, (category, len(before))
    kinds = sp["kind"] if sp else []
    suggest = outcome == "suggest"
    exp = {
        "outcome": outcome,
        "kind": kinds if suggest else [],
        "certainty": sp["certainty"] if suggest else None,
        "gold_places": [list(p) for p in sp["places"]] if suggest else [],
        "gold_words": sp["gold_words"] if suggest else None,
        "must_be_ambiguous": must_be_ambiguous,
        "must_not_be_exact": bool(suggest and sp["certainty"] == "probable"),
        "none_acceptable": none_acceptable,
        "identical_continuation": identical_continuation,
        "ok_status": ["suggest"] if suggest and not none_acceptable else (["suggest", "none"] if suggest else list(ok_status)),
        "note": note,
    }
    if suggest and sp.get("gold_words_by_place"):
        exp["gold_words_by_place"] = sp["gold_words_by_place"]
    if suggest and sp["kind"] == ["replace"]:
        exp["wrong_word"], exp["correct_word"] = sp["wrong_word"], sp["correct_word"]
    if suggest and sp["kind"] == ["insert"]:
        exp["skipped_words"] = sp["skipped"]
    specs = []
    if sp and not no_ts:
        specs.append(ts_out(sp, "typed" if suggest or category in ("complete_verse", "cue_non_quran_hadith_dua_proverb") else "quoted_or_looking"))
    if tail_sp:
        specs.append(ts_out(tail_sp, "tail_looking"))
    CASES.append({
        "id": f"SG-{len(CASES) + 1:03d}", "category": category, "before": before, "after": after, "explicit": explicit, "distinct": distinct,
        "context": {"cue": cue, "cue_kind": cue_kind or ("quran" if cue else None), "opener": opener or None, "separator": sep if cue else None,
                    "close": close or None},
        "typed_specs": specs, "expect": exp,
    })


def add_none(category, text, *, after="", explicit=False, distinct=False, note, ok_status=("none",), tail_sp=None, pre_sp=None):
    """A none-case written wholly by hand (optionally ending in a Quran-looking stretch)."""
    before = text + (tail_sp["typed"] if tail_sp else "")
    CASES.append({
        "id": f"SG-{len(CASES) + 1:03d}", "category": category, "before": before, "after": after, "explicit": explicit, "distinct": distinct,
        "context": {"cue": None, "cue_kind": None, "opener": None, "separator": None, "close": None},
        "typed_specs": [ts_out(tail_sp, "tail_looking")] if tail_sp else [],
        "expect": {"outcome": "none", "kind": [], "certainty": None, "gold_places": [], "gold_words": None, "must_be_ambiguous": False,
                   "must_not_be_exact": False, "none_acceptable": False, "identical_continuation": False, "ok_status": list(ok_status), "note": note},
    })


# =================================================================================================== A. exact continuation after a cue (22)
CA = "cue_continue"
N_A = "after an explicit Quran lead-in the typed words are an exact prefix of a single verse; the next words are offered as an exact continuation"
add(CA, cont(2, 153, 7, sty="dia"), pre="ومما يعين المسلم على تقلب الأحوال وطول الطريق أن يعود إلى كتاب ربه، ", cue="قال تعالى", opener="﴿",
    outcome="suggest", note=N_A + " (diacritized typing, 7 words)")
add(CA, cont(3, 200, 6, sty="plain"), pre="وفي بيان طريق الثبات أمام الصعاب يحسن بنا أن نتأمل ", cue="قوله تعالى", outcome="suggest",
    note=N_A + " (undiacritized typing)")
add(CA, cont(16, 90, 4, sty="dia"), pre="ولا يستقيم أمر مجتمع من غير ميزان للحقوق والواجبات، ", cue="يقول الله تعالى", after="\n", outcome="suggest",
    note=N_A + "; a newline follows the caret")
add(CA, cont(24, 35, 3, sty="plain"), pre="ومن الآيات التي أطال العلماء في تأمل تشبيهاتها وأسرارها، ", cue="قال الله عز وجل", opener="﴿", after="﴾",
    outcome="suggest", note=N_A + "; the editor has already closed the bracket after the caret")
add(CA, cont(17, 23, 3, sty="dia"), pre="وقد ورد الأمر ببر الوالدين مقرونًا بالتوحيد ", cue="في القرآن الكريم", outcome="suggest",
    note=N_A + " (3 words, diacritized)")
add(CA, cont(39, 53, 5, sty="plain"), pre="وما أوسع رحمة الله بعباده المذنبين إذا أقبلوا عليه نادمين، ", cue="قال سبحانه", opener="﴿", outcome="suggest",
    note=N_A)
add(CA, cont(13, 28, 4, sty="dia"), pre="وإذا ضاق الصدر بهموم الأيام فليتذكر صاحبه ", cue="قوله تعالى", outcome="suggest", note=N_A)
add(CA, cont(20, 25, 4, sty="dia"), pre="وكم من طالب علم يردد قبل دخول قاعة الاختبار ", cue="قوله تعالى على لسان موسى عليه السلام", opener="﴿",
    outcome="suggest", note=N_A + "; only the last word of the verse remains (a one-word continuation)")
add(CA, cont(59, 22, 8, sty="plain"), pre="وتختتم سورة الحشر بجملة من أسماء الله الحسنى، ", cue="قال الله تعالى", outcome="suggest",
    note=N_A + "; the verse opening is shared with another verse for its first 7 words, so only the 8-word prefix is distinctive")
add(CA, cont(49, 13, 8, sty="dia"), pre="ولا فضل لأحد على أحد بنسب أو لون أو جنس، ", cue="كما في قوله تعالى", opener="﴿", outcome="suggest", note=N_A)
add(CA, cont(67, 2, 4, sty="plain"), pre="وسورة الملك تذكّر بحكمة الابتلاء والعمل، ", cue="قال تعالى", sep="، ", outcome="suggest",
    note=N_A + "; cue followed by a comma")
add(CA, cont(112, 1, 3, sty="dia"), pre="وسورة الإخلاص خلاصة التوحيد في أربع كلمات، ", cue="قال تعالى", opener="﴿", after="﴾", outcome="suggest",
    note=N_A + " (short surah, one word left)")
add(CA, cont(93, 3, 3, sty="plain"), pre="وفي السورة التي نزلت تسليةً للنبي ﷺ بعد فتور الوحي ", cue="قال تعالى", outcome="suggest", note=N_A)
add(CA, cont(55, 26, 3, sty="dia"), pre="وتأمل زوال الدنيا وفناء كل ما فيها حين ", cue="يقول الله تعالى", outcome="suggest",
    note=N_A + " (short verse, one word left)")
add(CA, cont(18, 10, 5, sty="plain"), pre="ومن دروس قصة أهل الكهف اللجوء إلى الله عند اشتداد الفتنة، ", cue="في القرآن الكريم", opener="﴿", outcome="suggest", note=N_A)
add(CA, cont(94, 5, 2, sty="dia"), pre="ومن بشارات الصبر على المشقة ", cue="قال تعالى", outcome="suggest",
    note=N_A + "; only two words typed, but already unique in the whole text")
add(CA, cont(21, 87, 6, sty="plain"), pre="وقصة يونس عليه السلام من أعظم قصص التوبة والإنابة، ", cue="قال الله تعالى", outcome="suggest", note=N_A)
add(CA, cont(12, 4, 4, sty="dia"), pre="وتبدأ سورة يوسف بالرؤيا العجيبة، ", cue="قوله تعالى", opener="﴿", outcome="suggest", note=N_A)
# four typed the way they are copied from a Quran app (Uthmani script)
N_U = "typed in Uthmani script as copied from a Quran app (alef-wasla, waw + dagger alef, tatweel); same exact continuation expected"
add(CA, cont(2, 3, 5, sty="uth"), pre="ومن صفات المتقين في أول سورة البقرة ", cue="قال تعالى", opener="﴿", outcome="suggest", note=N_U + " (ٱلصَّلَوٰةَ)")
add(CA, cont(57, 20, 5, sty="uth"), pre="وفي بيان حقيقة الدنيا وزخرفها الزائل ", cue="قوله تعالى", outcome="suggest", note=N_U + " (ٱلْحَيَوٰةُ)")
add(CA, cont(98, 5, 11, sty="uth"), pre="وقد بيّن القرآن جوهر دعوة الأنبياء جميعًا، ", cue="يقول الله تعالى", opener="﴿", outcome="suggest", note=N_U + " (ٱلصَّلَوٰةَ)")
add(CA, cont(24, 37, 13, sty="uth"), pre="وهذه صفة رجال المساجد الذين شغلهم الله بطاعته، ", cue="قال تعالى", outcome="suggest", note=N_U + " (ٱلصَّلَوٰةِ، ٱلزَّكَوٰةِ)")

# =================================================================================================== B. continuation after an opening ﴿ « " (12)
CB = "opener_continue"
N_B = "no lead-in words, but the typed words follow an opening quotation mark and are an exact prefix of a single verse"
add(CB, cont(63, 9, 8, sty="dia"), pre="وحسبك في التحذير من الانشغال عن الله آية واحدة: ", opener="﴿", outcome="suggest", note=N_B + " (﴿)")
add(CB, cont(65, 3, 5, sty="plain"), pre="كتب لي صديق في أزمته المالية فأجبته بهذه الآية: ", opener="﴿", outcome="suggest", note=N_B + " (﴿, undiacritized)")
add(CB, cont(33, 56, 7, sty="dia"), pre="وللصلاة على النبي ﷺ مكانة خاصة في الدين: ", opener="﴿", after="﴾", outcome="suggest", note=N_B + " (﴿, closing bracket already after the caret)")
add(CB, cont(25, 63, 7, sty="dia"), pre="وانظر إلى وصف القرآن لأهل الاتزان والوقار: ", opener="﴿", outcome="suggest", note=N_B + " (﴿)")
add(CB, cont(14, 7, 5, sty="plain"), pre="وقاعدة الشكر في الرزق واضحة لا لبس فيها: ", opener="﴿", outcome="suggest", note=N_B + " (﴿)")
add(CB, cont(49, 10, 3, sty="dia"), pre="وأقصر ما يوصي به المصلحون بين المتخاصمين: ", opener="﴿", outcome="suggest", note=N_B + " (﴿, 3 words)")
add(CB, cont(42, 40, 4, sty="dia"), pre="وهذا ميزان الإنصاف حين نختلف ونتخاصم، وهو ", opener="«", outcome="suggest", note=N_B + " («)")
add(CB, cont(64, 16, 4, sty="plain"), pre="ومن أيسر التكاليف أنها على قدر الوسع: ", opener="«", outcome="suggest", note=N_B + " («)")
add(CB, cont(11, 114, 5, sty="dia"), pre="وتعلّمنا الآية أن الطاعة تمحو الزلل، ", opener="«", after="»", outcome="suggest", note=N_B + " («, closing guillemet already after the caret)")
add(CB, cont(8, 2, 5, sty="dia"), pre="وللإيمان علامات في القلب والجوارح، وأولها ", opener='"', outcome="suggest", note=N_B + ' (straight double quote ")')
add(CB, cont(32, 16, 2, sty="plain"), pre="ومن وصف قيام الليل ما جاء في سورة السجدة: ", opener="“", outcome="suggest", note=N_B + " (curly double quote; only 2 words but unique)")
add(CB, cont(47, 7, 7, sty="plain"), pre="وأما النصر فسبيله معروف، وقد كتب أحدهم في مقدمة كتابه ", opener='"', outcome="suggest", note=N_B + ' (straight double quote ")')

# =================================================================================================== C. caret inside the last word (8)
CC = "partial_word"
N_C = "the caret is inside the last typed word, which is a prefix of the verse word; the word is to be completed (kind complete_word)"
add(CC, part(3, 200, 5, 4, sty="plain"), pre="وللصبر ثلاث مراتب وردت في آية واحدة، ", cue="قال تعالى", opener="﴿", outcome="suggest", note=N_C)
add(CC, part(16, 90, 4, 5, sty="dia"), pre="وهو أعظم ما قيل في جماع الأخلاق، ", cue="يقول الله تعالى", outcome="suggest", note=N_C)
add(CC, part(49, 13, 7, 3, sty="plain"), pre="ومما يقرب بين الناس على اختلاف ألوانهم ", cue="في القرآن الكريم", sep=": ", opener="﴿", after="﴾", outcome="suggest",
    note=N_C + "; closing bracket after the caret")
add(CC, part(31, 13, 5, 3, sty="dia"), pre="وهذه وصية الأب الحكيم لابنه، ", cue="قال تعالى", outcome="suggest", note=N_C)
add(CC, part(51, 56, 5, 4, sty="plain"), pre="وغاية الخلق وحكمتها ", cue="قوله تعالى", opener="﴿", outcome="suggest", note=N_C)
add(CC, part(67, 2, 3, 4, sty="dia"), pre="وهكذا ينبغي أن ينظر المرء إلى المصائب والنعم، ", cue="قال سبحانه", opener="", outcome="suggest", note=N_C)
add(CC, part(35, 28, 12, 5, sty="plain"), pre="وأولى الناس بخشية الله أعرفهم به، ", opener="﴿", outcome="suggest", note=N_C + "; opening bracket instead of a lead-in")
add(CC, part(48, 29, 9, 3, sty="dia"), pre="وانظر كيف صوّر القرآن حال الصحابة الكرام، ", cue="في القرآن الكريم", sep=": ", opener="﴿", outcome="suggest", note=N_C)

# =================================================================================================== D. wrong last word (replace) (14)
CD = "wrong_word_replace"
N_D = "a distinctive exact prefix, then a wrong word followed by a space: a PROBABLE correction (kind replace) of the wrong word to the verse word"
add(CD, wrong(40, 60, 9, "لعبادتي", sty="plain"), pre="ومما يشجع على السؤال والدعاء أن ربنا أمر به وضمن الإجابة، ", cue="قال تعالى", opener="﴿", outcome="suggest",
    note=N_D + " (singular noun with a wrongly attached lam)")
add(CD, wrong(3, 200, 10, "ترحمون", sty="dia"), pre="وهذه خاتمة السورة وفيها جماع الوصايا، ", cue="قال تعالى", opener="﴿", outcome="suggest", note=N_D + " (a different closing word)")
add(CD, wrong(16, 90, 7, "القربة", sty="plain"), pre="ولا غنى لأي مجتمع عن هذا الميزان الجامع، ", cue="يقول الله تعالى", outcome="suggest", note=N_D + " (a letter changed)")
add(CD, wrong(33, 56, 5, "الرسول", sty="dia"), pre="وهو أمر موجّه للمؤمنين جميعًا، ", cue="قوله تعالى", opener="﴿", outcome="suggest", note=N_D + " (a synonym of the verse word)")
add(CD, wrong(13, 28, 5, "ربهم", sty="plain"), pre="وهذا هو الدواء الذي يصفه القرآن لقلق النفوس، ", cue="قال الله تعالى", outcome="suggest", note=N_D + " (a plausible slip)")
add(CD, wrong(29, 69, 4, "سبيلنا", sty="dia"), pre="ومن بشارات المجاهدين في سبيل الله، ", cue="قال تعالى", opener="﴿", outcome="suggest", note=N_D + " (singular for plural)")
add(CD, wrong(51, 56, 5, "ليعبدوا", sty="plain"), pre="وهذه الغاية التي من أجلها خلق الله الخلق، ", cue="في القرآن الكريم", outcome="suggest", note=N_D + " (a different verb ending)")
add(CD, wrong(93, 3, 3, "ولا", sty="dia"), pre="وقد نزلت السورة في تثبيت قلب النبي ﷺ، ", cue="قال تعالى", sep=": ", opener="﴿", outcome="suggest", note=N_D + " (one conjunction for another)")
add(CD, wrong(17, 23, 7, "برا", sty="plain"), pre="وحق الوالدين لا يسبقه إلا حق الله، ", cue="قوله تعالى", outcome="suggest",
    note=N_D + " (a shorter synonym)")
add(CD, wrong(24, 35, 5, "ضوئه", sty="dia"), pre="ومن أجمل أمثلة القرآن للنور والهداية ", cue="قال الله عز وجل", opener="﴿", outcome="suggest", note=N_D + " (a synonym)")
add(CD, wrong(49, 10, 3, "فسالموا", sty="plain"), pre="وهو ما ينبغي أن يُقال لكل متخاصمين، ", cue="قال سبحانه", outcome="suggest", note=N_D + " (a different verb)")
add(CD, wrong(25, 63, 6, "لينا", sty="dia"), pre="ومن ثناء الله على أهل التواضع ", cue="يقول الله تعالى", opener="﴿", outcome="suggest", note=N_D + " (a near-synonym)")
add(CD, wrong(67, 2, 6, "أفضل", sty="plain"), pre="والابتلاء ميزان العمل لا ميزان الكثرة، ", cue="قال تعالى", outcome="suggest", note=N_D + " (a synonym)")
add(CD, wrong(39, 53, 8, "تيأسوا", sty="dia"), pre="فما أحوج المذنبين إلى هذا النداء الرحيم، ", cue="قال تعالى", opener="﴿", outcome="suggest", note=N_D + " (a synonym)")

# =================================================================================================== E. missing word (insert) (8)
CE = "missing_word_insert"
N_E = "a distinctive exact prefix, then the verse word that follows one or two omitted words (and a space): a PROBABLE insertion (kind insert) of the omitted words"
add(CE, miss(2, 153, 5, 1, sty="plain"), pre="ومن أعظم ما يقوّي القلب في الشدائد ", cue="قال تعالى", opener="﴿", outcome="suggest", note=N_E + " (one word omitted)")
add(CE, miss(16, 90, 4, 1, sty="dia"), pre="وهي الآية التي تُقرأ في ختام الخطب، ", cue="يقول الله تعالى", outcome="suggest", note=N_E + " (one word omitted)")
add(CE, miss(4, 58, 5, 1, sty="plain"), pre="وفي باب الأمانة والعدل أصل عظيم ", cue="قوله تعالى", outcome="suggest", note=N_E + " (one word omitted)")
add(CE, miss(17, 23, 4, 1, sty="dia"), pre="وقد بدأ بأعظم الحقوق قبل ذكر الوالدين، ", cue="قال الله تعالى", opener="﴿", outcome="suggest", note=N_E + " (one word omitted)")
add(CE, miss(31, 13, 6, 1, sty="plain"), pre="وهذه أولى وصايا لقمان لابنه، ", cue="في القرآن الكريم", outcome="suggest", note=N_E + " (one word omitted)")
add(CE, miss(49, 13, 5, 2, sty="dia"), pre="وهو نداء لعموم البشر لا للمسلمين وحدهم، ", cue="قال تعالى", opener="﴿", outcome="suggest", note=N_E + " (two words omitted)")
add(CE, miss(67, 2, 3, 1, sty="plain"), pre="والموت والحياة كلاهما ميدان للاختبار، ", cue="يقول الله", outcome="suggest", note=N_E + " (one word omitted)")
add(CE, miss(25, 63, 3, 2, sty="dia"), pre="ويصف القرآن عباد الله الصالحين وصفًا بديعًا، ", cue="قال تعالى", opener="﴿", outcome="suggest", note=N_E + " (two words omitted)")

# =================================================================================================== F. ambiguous openings (10)
CF = "ambiguous_opening"
N_F = "the typed words begin several different verses; the answer must offer choices from different places or nothing — never one confident exact choice that picks a place arbitrarily"


def add_amb(sp, **kw):
    add(CF, sp, outcome="suggest", must_be_ambiguous=True, none_acceptable=True, note=N_F + f" ({len(sp['places'])} places)", **kw)


add_amb(amb(15, 9, 3, [(15, 9, 9), (76, 23, 23)], sty="dia"), pre="وقد وعد الله بحفظ كتابه إذ ", cue="قال تعالى", opener="﴿")
add_amb(amb(13, 12, 3, [(13, 12, 12), (40, 13, 13)], sty="plain"), pre="ومن دلائل القدرة ما يراه الناس في السماء من برق ورعد، ", cue="قوله تعالى")
add_amb(amb(21, 14, 3, [(21, 14, 14), (36, 52, 52), (68, 31, 31)], sty="dia"), pre="وهذا حال الظالمين حين يفاجئهم الحق، ", cue="يقول الله تعالى")
add_amb(amb(2, 126, 3, [(2, 126, 126), (2, 260, 260), (6, 74, 74), (14, 35, 35), (43, 26, 26)], sty="plain"), pre="وكثيرًا ما يذكّرنا القرآن بأبي الأنبياء، ", cue="قال تعالى", opener="﴿")
add_amb(amb(29, 4, 3, [(29, 4, 4), (45, 21, 21), (47, 29, 29)], sty="dia"), pre="ومن سنن الله في خلقه أنه يختبر الناس ويكشفهم، ", cue="في القرآن الكريم")
add_amb(amb(26, 160, 3, [(26, 160, 160), (54, 33, 33)], sty="plain"), pre="وفي قصص الأمم السابقة عبرة لمن اعتبر، ", cue="قال الله تعالى", opener="﴿")
add_amb(amb(16, 41, 3, [(16, 41, 41), (22, 58, 58)], sty="dia"), pre="وللمهاجرين في سبيل الله وعد كريم، ", cue="قوله تعالى")
add_amb(amb(4, 92, 3, [(4, 92, 92), (33, 36, 36)], sty="plain"), pre="وهي أحكام ملزمة لكل من يقول إنه مؤمن، ", cue="قال سبحانه", opener="﴿")
add_amb(amb(19, 90, 3, [(19, 90, 90), (42, 5, 5)], sty="dia"), pre="وفي تعظيم الشرك بالله وصف شديد، ", cue="يقول الله تعالى")
add_amb(amb(7, 84, 3, [(7, 84, 84), (26, 173, 173), (27, 58, 58)], sty="plain"), pre="وعاقبة المكذبين مذكورة في أكثر من سورة، ", cue="قال تعالى")

# =================================================================================================== G. repeated / near-repeated verses (4)
CG = "repeated_verses"
N_G = "the same words occur at many places"
# a refrain repeated word for word: the words that follow are the same at every place, the place itself is not determined
add(CG, amb(55, 13, 3, [(55, n, n) for n in (13, 16, 18, 21, 23, 25, 28, 30, 32, 34, 36, 38, 40, 42, 45, 47, 49, 51, 53, 55, 57, 59, 61, 63, 65, 67, 69, 71, 73, 75, 77)], sty="dia"),
    pre="وسورة الرحمن تكرر سؤالًا واحدًا لا تملك النفس إلا أن تجيب عنه، ", cue="قال تعالى", opener="﴿", outcome="suggest", must_be_ambiguous=True,
    none_acceptable=True, identical_continuation=True, note=N_G + ": the 31-fold refrain of surah 55; the continuation is identical at every place but the verse is not determined")
add(CG, amb(77, 15, 2, [(77, n, n) for n in (15, 19, 24, 28, 34, 37, 40, 45, 47, 49)] + [(83, 10, 10)], sty="plain"),
    pre="وفي سورة المرسلات يتكرر الوعيد مرة بعد مرة، ", cue="قال الله تعالى", outcome="suggest", must_be_ambiguous=True, none_acceptable=True,
    identical_continuation=True, note=N_G + ": the refrain of surah 77 (10 times) and one verse of surah 83; the continuation is identical everywhere")
# near-repeats whose continuations differ
add(CG, amb(69, 3, 3, [(69, 3, 3), (74, 27, 27), (77, 14, 14), (82, 17, 17), (83, 8, 8), (83, 19, 19), (86, 2, 2), (90, 12, 12), (97, 2, 2), (101, 3, 3),
                       (101, 10, 10), (104, 5, 5)], sty="dia"),
    pre="وفي قصار السور أسلوب تعظيم يتكرر، ", cue="في القرآن الكريم", outcome="suggest", must_be_ambiguous=True, none_acceptable=True,
    note=N_G + ": the question formula of 12 verses; the continuation differs from place to place (near-repeat)")
add(CG, amb(10, 67, 5, [(10, 67, 67), (13, 3, 3), (13, 4, 4), (16, 12, 12), (16, 79, 79), (27, 86, 86), (29, 24, 24), (30, 21, 21), (30, 23, 23),
                        (30, 24, 24), (30, 37, 37), (39, 42, 42), (39, 52, 52), (45, 13, 13)], w0=9, sty="plain"),
    pre="وتختم كثير من الآيات الكونية بنهاية متقاربة، ", cue="قوله تعالى", outcome="suggest", must_be_ambiguous=True, none_acceptable=True,
    note=N_G + ": the clause that closes many signs-of-creation verses (14 places, four different endings)")

# =================================================================================================== H. complete verse (4)
CH = "complete_verse"
N_H = "the whole verse is already written; nothing is left to add"
add(CH, full(108, 1, "dia", trail=""), pre="وأقصر سور القرآن عبارةً عن آية واحدة هي ", cue="قوله تعالى", opener="﴿", close="", after="﴾", outcome="none", note=N_H)
add(CH, full(103, 2, "plain", trail=" "), pre="وفي سورة العصر خلاصة الرسالة، ", cue="قال تعالى", outcome="none", note=N_H + " (a trailing space after the last word)")
add(CH, full(68, 4, "dia", trail=""), pre="وهو ثناء من الله على خلق نبيه ﷺ، ", cue="يقول الله تعالى", opener="«", after="»", outcome="none", note=N_H)
add(CH, full(36, 58, "plain", trail=""), pre="وهي تحية أهل الجنة، ", cue="في القرآن الكريم", outcome="none", note=N_H)

# =================================================================================================== I. hadith / du'a / proverb cue before Quran-looking words (8)
CI = "cue_non_quran_hadith_dua_proverb"
N_I = "the cue is a hadith / du'a / proverb cue, not a Quran lead-in: Quran-looking words after it must not be completed"
add(CI, cont(49, 13, 5, sty="plain"), pre="وفي حجة الوداع وقف في الناس خطيبًا، ثم ", cue="قال رسول الله ﷺ", cue_kind="hadith", outcome="none", note=N_I + " (hadith cue)")
add(CI, cont(33, 56, 4, sty="plain"), pre="روى الإمام أحمد في مسنده عن أبي هريرة رضي الله عنه، ", cue="قال رسول الله ﷺ", sep=" لأصحابه: ", cue_kind="hadith", outcome="none",
    note=N_I + " (hadith cue)")
add(CI, cont(3, 200, 5, sty="dia"), pre="ويؤكد هذا المعنى ما جاء في السنة، ", cue="وفي الحديث الشريف", sep=": ", cue_kind="hadith", outcome="none", note=N_I + " (hadith cue)")
add(CI, cont(3, 8, 3, sty="plain"), pre="ومن أدعية الصباح التي يرددها كثير من الناس ", cue="اللهم", sep=" ", cue_kind="dua", outcome="none", note=N_I + " (du'a cue «اللهم»)")
add(CI, cont(20, 25, 3, w0=1, sty="plain"), pre="وكان يختم دعاءه بالطلب نفسه، ", cue="ومن الدعاء", sep=": ", cue_kind="dua", outcome="none", note=N_I + " (du'a cue «دعاء»)")
add(CI, cont(7, 23, 4, w0=1, sty="dia"), pre="ويحفظ كثير من العامة هذه الجملة في دعائهم، ", cue="اللهم", sep=" ", cue_kind="dua", outcome="none", note=N_I + " (du'a cue «اللهم»)")
add(CI, cont(42, 40, 3, sty="plain"), pre="وقد صارت عبارة مأثورة على ألسنة الناس، ", cue="كما يقول المثل", sep=": ", cue_kind="proverb", outcome="none", note=N_I + " (proverb cue)")
add(CI, cont(55, 60, 3, sty="dia"), pre="ويختصر الناس هذا المعنى في عبارة سائرة، ", cue="وكما في الحكمة السائرة", sep=": ", cue_kind="proverb", outcome="none",
    note=N_I + " (proverb cue)")

# =================================================================================================== J. everyday formulas / ordinary Islamic prose without cue (16)
CJ = "everyday_no_cue"
N_J = "ordinary prose or an everyday formula with common Quran words, no Quran lead-in or opening mark, distinct=false: no suggestion"
J = [
    ("تلقيت صباح اليوم رسالة من الإدارة بقبول طلبي ونقلي إلى الفرع الجديد، والحمد لله رب ", None),
    ("سنلتقي غدًا بعد صلاة الفجر إن شاء الله ونكمل الحديث في موضوع الميزانية والتكاليف", None),
    ("شكرًا لك على الملف الذي أرسلته قبل الظهر، وجزاك الله خيرًا على هذا الجهد الكبير", None),
    ("حاولت إصلاح الجهاز مرتين دون فائدة، ولا حول ولا قوة إلا ", None),
    ("بسم الله الرحمن ", None),
    ("الذين يعملون في المصنع قدّموا طلبًا لزيادة الأجور وتحسين ساعات الدوام، وقد وعدتهم الإدارة بدراسة ", None),
    ("لا أشك في أن الله غفور رحيم بعباده، لكننا نحتاج مع ذلك إلى مراجعة أنفسنا بين الحين والآخر وإلى ", None),
    ("يا أيها الناس انتبهوا من فضلكم، فالمطعم سيغلق أبوابه مبكرًا هذا المساء بسبب أعمال الصيانة ", None),
    ("نسأل الله العلي القدير أن يتقبل منا ومنكم صالح الأعمال وأن يجمعنا على الخير في ", None),
    ("وبعد التخرج سافر إلى الرياض وعمل في شركة كبيرة، ثم عاد إلى بلدته وافتتح مكتبًا للمحاسبة، وهو يدير اليوم ", None),
    ("يحرص طلاب المدرسة على أداء الصلاة في وقتها ثم يذهبون إلى فصولهم في هدوء وانتظام، وفي ", None),
    ("رأيت الحديقة بعد المطر فقلت لصاحبي: ما شاء الله لا قوة إلا ", None),
    ("وصلنا خبر وفاة والدكم، عظّم الله أجركم وأحسن عزاءكم، وإنا لله وإنا إليه ", None),
    ("بعد كل صلاة أردد التسبيحات المعروفة: سبحان الله وبحمده سبحان الله ", None),
    ("وأخيرًا أختم رسالتي بالتحية المعتادة: السلام عليكم ورحمة ", None),
    ("وإذا انتهينا من مراجعة العقد والملاحق فسنطلب حضور اجتماع قصير يوم الأحد، ثم نعرض الأمر على الذين ", None),
]
assert len(J) == 16
J_NOTES = [
    "the text ends inside the opening formula «الحمد لله رب العالمين», with no lead-in",
    "everyday formula «إن شاء الله» inside prose",
    "everyday formula «جزاك الله خيرًا» inside prose",
    "the text ends inside «لا حول ولا قوة إلا بالله» typed as an everyday formula",
    "the basmala typed at the very start, with no lead-in",
    "ordinary prose that begins a clause with «الذين» (a very common Quran word)",
    "ordinary prose that contains «الله غفور رحيم» as a plain sentence, with no lead-in",
    "ordinary prose beginning «يا أيها الناس», a common vocative",
    "ordinary Islamic prayer wishes in prose",
    "plain biographical prose",
    "ordinary school prose mentioning prayer",
    "everyday expression «ما شاء الله» followed by the start of «لا قوة إلا بالله»",
    "condolence formula «إنا لله وإنا إليه راجعون» typed with no lead-in",
    "tasbih words typed in everyday worship talk",
    "greeting formula «السلام عليكم ورحمة الله وبركاته»",
    "ordinary office prose that ends with the very common word «الذين»",
]
for (txt, _), n in zip(J, J_NOTES):
    add_none(CJ, txt, note=N_J + ": " + n)

# =================================================================================================== K. distinct=true with a long exact prefix and no cue (6) + same without distinct (3)
CK = "distinct_long_prefix"
CK2 = "no_distinct_same_prefix"
N_K = "no cue and no opening mark, but distinct=true and the typed words are a long exact prefix of one verse: a continuation is expected"
K = [
    (cont(24, 35, 8, sty="plain"), "جلست أرتب أوراقي فوجدت في دفتر قديم هذه الكلمات: ", ""),
    (cont(2, 255, 10, sty="dia"), "وكتبت في آخر الصفحة، قبل أن أنام، هذه الكلمات الطويلة: ", ""),
    (cont(48, 29, 9, sty="plain"), "ثم وجدت ورقة صغيرة مطوية كتب عليها بخط جميل: ", "\n"),
    (cont(46, 15, 9, sty="dia"), "وفي حاشية الكتاب كتب أحدهم بخط صغير: ", ""),
    (cont(31, 13, 7, sty="plain"), "وأرسل لي أخي رسالة قصيرة نصها: ", ""),
    (cont(57, 20, 8, sty="dia"), "وعلى باب المكتبة علّقوا لوحة مكتوبًا فيها: ", ""),
]
for sp, pre, aft in K:
    add(CK, sp, pre=pre, after=aft, distinct=True, outcome="suggest", note=N_K)
# the same text, same position, distinct=false: nothing may be suggested (first three of K)
for (sp, pre, aft), n in zip(K[:3], range(3)):
    add(CK2, sp, pre=pre, after=aft, distinct=False, outcome="none",
        note="identical text to the matching distinct=true case, but without distinct and without any cue or opening mark: no suggestion")

# =================================================================================================== L. text after a closed bracket / full stop (5)
CL = "after_closed_quotation"
N_L = "the quotation or sentence is closed; the words typed afterwards are ordinary writing even though they look like the start of a verse"
add(CL, full(94, 5, "dia", trail=""), pre="وهذه بشارة عظيمة لأهل الصبر، ", cue="قال تعالى", opener="﴿", close="﴾", tail=". ومن ذلك أن تكون صادقًا مع نفسك، ",
    tail_sp=slice_(16, 90, 0, 3, "plain"), outcome="none", note=N_L + " (bracket closed, then a new sentence)")
add(CL, full(112, 1, "dia", trail=""), pre="ولخّص الإسلام العقيدة في أربع كلمات: ", cue=None, opener="«", close="»", tail="، وهي كافية لمن تأمل، ولكل أمر ميزان: ",
    tail_sp=slice_(49, 10, 0, 3, "plain"), outcome="none", note=N_L + " (guillemet closed)")
add(CL, slice_(67, 2, 0, 3, "plain", trail=" "), pre="أكتب في هذا الأسبوع عن الموت والحياة. ", cue="قال تعالى", sep=". ", outcome="none",
    note=N_L + " (the lead-in sentence is ended by a full stop before the Quran-looking words)")
add(CL, full(103, 2, "dia", trail=""), pre="وقال تعالى مبيّنًا خسران الإنسان: ", cue=None, opener='"', close='"', tail=" هذه هي القاعدة، ثم نصل إلى الخلاصة وهي أن ",
    tail_sp=slice_(103, 3, 0, 3, "plain"), outcome="none", note=N_L + " (straight quotes closed)")
add(CL, slice_(20, 25, 0, 4, "dia", trail=""), pre="وللنبي موسى دعاء قديم نردده، ", cue="قوله تعالى", opener="﴿", close="﴾.", tail=" وبعد ذلك انتقل المحاضر إلى المحور الثاني، ",
    tail_sp=slice_(65, 3, 0, 4, "plain"), outcome="none", note=N_L + " (bracket and full stop)")

# =================================================================================================== M. explicit=true, short but sufficient prefix (6) and one word (3)
CM = "explicit_short_prefix"
N_M = "explicit=true (the writer asked for a suggestion), no cue; two or three words that already single out one verse"
add(CM, cont(9, 128, 2, sty="plain"), pre="كنت أريد أن أتذكر بقية الآية: ", explicit=True, outcome="suggest", note=N_M)
add(CM, cont(36, 58, 2, sty="plain"), pre="لا أذكر تمام العبارة، ", explicit=True, outcome="suggest", note=N_M)
add(CM, cont(51, 56, 2, sty="dia"), pre="ساعدني في إكمال هذا الموضع: ", explicit=True, outcome="suggest", note=N_M)
add(CM, cont(60, 8, 2, sty="plain"), pre="وردت هذه القاعدة في الممتحنة وأريد تمامها: ", explicit=True, outcome="suggest", note=N_M)
add(CM, cont(3, 92, 2, sty="dia"), pre="أحفظ بداية الآية فقط: ", explicit=True, outcome="suggest", note=N_M)
add(CM, cont(29, 69, 2, sty="plain"), pre="", explicit=True, outcome="suggest", note=N_M + " (nothing but the typed words)")
CM1 = "explicit_one_word"
N_M1 = "explicit=true but a single word: far too ambiguous to propose anything (none, or at most a hint asking for more words)"
for pre, w, ts in [("اكتب لي إكمالًا لهذه العبارة: ", "الذين ", slice_(2, 3, 0, 1, "plain")),
                   ("وردت في المصحف كلمة تبدأ بها آيات كثيرة: ", "وقالوا ", slice_(2, 80, 0, 1, "plain")),
                   ("", "إن ", slice_(3, 19, 0, 1, "plain"))]:
    CASES.append({
        "id": f"SG-{len(CASES) + 1:03d}", "category": CM1, "before": pre + w, "after": "", "explicit": True, "distinct": False,
        "context": {"cue": None, "cue_kind": None, "opener": None, "separator": None, "close": None},
        "typed_specs": [{**ts["ts"], "role": "tail_looking"}],
        "expect": {"outcome": "none", "kind": [], "certainty": None, "gold_places": [], "gold_words": None, "must_be_ambiguous": False,
                   "must_not_be_exact": False, "none_acceptable": False, "identical_continuation": False, "ok_status": ["none", "hint"], "note": N_M1},
    })

# --------------------------------------------------------------------------------------------- freeze
counts = Counter(c["category"] for c in CASES)
surahs = set()
for c in CASES:
    for t in c["typed_specs"]:
        surahs.add(t["surah"])
    for p in c["expect"]["gold_places"]:
        surahs.add(p[0])
assert len(surahs) >= 40, len(surahs)

ABOUT = (
    "Frozen evaluation set for POST /api/suggest (verse suggestions computed ONLY from the Quranpedia Hafs text, no AI), v1, written "
    "3 October 2026, by an unknown author (found uncommitted in the working tree on 3 Oct 2026 at 15:16; its file modification time is LATER than that of app/suggest.py, so the claim made when it was written, that it was blind to the implementation, could NOT be verified and is NOT relied on): treat this as a DEVELOPMENT set, not as untouched held-out data. "
    "AUTHOR-WRITTEN BY AN AI-ASSISTED WORKFLOW (the same assistant wrote the contract examples, the prose and the labels): NOT an independent sample; "
    "the labels await review by a human Arabic / Quran specialist. The SHA-256 of this file is in eval/suggest_cases_20261003.sha256. "
    "Only COORDINATES are stored for gold (gold_places = [surah, ayah_start, ayah_end]; gold_words = [surah, ayah, word_from, word_to) over the "
    "Quranpedia word list of that ayah); no Quran corpus is stored. The `before` strings necessarily contain the Quran words the writer is supposed to "
    "have typed (cut from the Quranpedia text by eval/build_suggest_cases.py by coordinates, as eval/articles_frozen.json does); wrong / missing / "
    "partial-word variants are explicit edits (typed_specs[].edit) applied to those words. Arabic prose around the cues is hand-written. "
    "Labels are cross-checked by eval/validate_suggest_cases.py, which does not use the app's matching code. "
    "Contract encoded: after an explicit Quran lead-in or an opening mark, >= 2 distinctive words -> the next words are an EXACT continuation "
    "(kind continue; complete_word when the caret is inside the last word); a distinctive prefix followed by a wrong word (then a space) -> PROBABLE "
    "replace, or PROBABLE insert when the typed word is the verse word after one or two skipped words; ambiguous openings -> several choices from "
    "different places (ambiguous=true) or nothing, never one confident exact choice; hadith / du'a / proverb cues, everyday formulas, text after a closed "
    "quotation or sentence, text with no cue/opener (distinct=false), complete verses and a single word -> none (a hint is also accepted only for the "
    "explicit one-word cases). Cases with none_acceptable=true (ambiguous, repeated) may also legitimately return none. "
    "expect fields: outcome (suggest|none); kind = acceptable kinds of the best choice; certainty = expected certainty of the best choice; gold_places = places "
    "that must be among the choices; gold_words = the Quran words that the proposed text (to_text, else insert_text) must start with (for complete_word: the "
    "whole word, or its missing suffix); wrong_word/correct_word for replace; skipped_words for insert; ok_status = response statuses that are not a false "
    "suggestion. Metrics are defined in eval/run_suggest_eval.py. No threshold or rule may be tuned against this file."
)

data = {"_about": ABOUT, "version": 1, "written": "2026-10-03", "categories": dict(counts), "cases": CASES}
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"wrote {OUT.relative_to(ROOT)}: {len(CASES)} cases, {len(surahs)} surahs")
for k, v in counts.items():
    print(f"  {k}: {v}")
