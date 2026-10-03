"""Builds eval/suggest_cases_b_20261003.json: SET B, a second frozen evaluation set for POST /api/suggest (verse suggestions
while the writer types), written 2026-10-03 by an AI subagent (Claude) in a fresh context, independently of set A
(eval/suggest_cases_20261003.json) and under the instruction NOT to read the implementation of the feature.

Labels come from (1) the Quranpedia Hafs text and (2) the written contract (the `_about` of set A, the docstring of
eval/validate_suggest_cases.py). They are NOT the result of observing what the implementation returns.

Quran words are never typed from memory: every Quran string in a `before` text is cut from the Quranpedia Hafs text by coordinates
(surah, ayah, first word, last word), and, for the wrong-word / missing-word / partial-word cases, by an explicit edit applied to
those words. The Arabic prose around the Quran words is hand-written. The builder asserts the properties it relies on (unique
places, ambiguity, non-existence of the typed variants) over the folded per-surah word streams, and asserts that no ayah used here
(typed, quoted, tail, gold) occurs in set A (read from set A's JSON). The independent validator
(eval/validate_suggest_cases.py) re-checks the labels with its own code.

    .venv/bin/python eval/build_suggest_cases_b_20261003.py     # writes eval/suggest_cases_b_20261003.json
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
OUT = ROOT / "eval" / "suggest_cases_b_20261003.json"
SET_A = ROOT / "eval" / "suggest_cases_20261003.json"

# ---------------------------------------------------------------------------------------------- set A coordinates to avoid
A_AYAHS: set[tuple[int, int]] = set()
for _c in json.loads(SET_A.read_text(encoding="utf-8"))["cases"]:
    for _p in _c["expect"]["gold_places"]:
        for _a in range(_p[1], _p[2] + 1):
            A_AYAHS.add((_p[0], _a))
    for _t in _c["typed_specs"]:
        A_AYAHS.add((_t["surah"], _t["ayah"]))

# ---------------------------------------------------------------------------------------------- own folding (escapes only)
MARKS = re.compile("[ً-ٰٟۖ-ۭـ﻿]")
FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي",
                      "ة": "ه", "ؤ": "و", "ئ": "ي"})


def fold_words(t: str) -> list[str]:
    """Folded words: waw + dagger alef -> alef, alef variants -> alef, marks dropped, ى->ي ة->ه ؤ->و ئ->ي."""
    t = re.sub("و[ً-ٟ]*ٰ", "ا", t)
    return re.sub("[^ء-ي ]", " ", MARKS.sub("", t).translate(FOLD)).split()


def strip(t: str) -> str:
    return MARKS.sub("", t)


def W(s: int, a: int) -> list[str]:
    return idx.ayahs[(s, a)].words


streams: dict[int, list[tuple[str, int, int]]] = {}
for (_s, _n), _a in sorted(idx.ayahs.items()):
    for _i, _w in enumerate(_a.words):
        _fw = fold_words(_w)
        assert len(_fw) == 1, (_s, _n, _w, _fw)
        streams.setdefault(_s, []).append((_fw[0], _n, _i))
STREAM_WORDS = {s: [x[0] for x in st] for s, st in streams.items()}


def occurrences(ws: list[str], last_prefix: bool = False) -> list[tuple[int, int, int]]:
    """Places (surah, first ayah, last ayah) where the folded words occur contiguously; with last_prefix the final word
    only has to START with the last given string."""
    out = []
    n = len(ws)
    h = n - (1 if last_prefix else 0)
    for s, fw in STREAM_WORDS.items():
        st = streams[s]
        for i in range(len(fw) - n + 1):
            if fw[i:i + h] != ws[:h]:
                continue
            if last_prefix and not fw[i + n - 1].startswith(ws[-1]):
                continue
            out.append((s, st[i][1], st[i + n - 1][1]))
    return out


def not_in_a(s: int, a: int) -> None:
    assert (s, a) not in A_AYAHS, ("ayah also used in set A", s, a)


# ---------------------------------------------------------------------------------------------- typing styles
UTH = [("صَّلَاة", "صَّلَوٰة"),    # صَّلَاة -> صَّلَوٰة
       ("زَّكَاة", "زَّكَوٰة"),    # زَّكَاة -> زَّكَوٰة
       ("حَيَاة", "حَيَوٰة")]
# alef-wasla: the alef of the article (optionally after wa/fa/bi/ka) and of verbs whose second letter carries a sukun
WASLA_ARTICLE = re.compile("^(?:[وف]َ|بِ|كَ)?ا(?=ل(?:ْ|[َّ]{1,2})?[ء-ي])")
WASLA_VERB = re.compile("^ا(?=[ء-ي]ْ)")


def style_word(w: str, sty: str) -> str:
    if sty == "dia":
        return w
    if sty == "plain":
        return strip(w)
    if sty == "uth":  # Uthmani-script spelling as copied from a Quran app: alef-wasla, waw + dagger alef
        orig = w
        for a, b in UTH:
            w = w.replace(a, b)
        m = WASLA_ARTICLE.match(w) or WASLA_VERB.match(w)
        if m:
            i = m.end() - 1
            w = w[:i] + "ٱ" + w[i + 1:]
        assert fold_words(w) == fold_words(orig), (w, orig)
        return w
    raise ValueError(sty)


def vocalised_cut(word: str, letters: int) -> str:
    """The first `letters` base letters of a diacritized word, with their marks, except that the last letter is bare."""
    out, n = "", 0
    for ch in word:
        if not (MARKS.match(ch)):
            if n == letters:
                break
            n += 1
            out += ch
        elif n < letters:
            out += ch
        # marks after the last kept letter are dropped (the writer has not typed its vowel yet)
    # drop marks that directly follow the last letter
    j = len(out)
    while j > 0 and MARKS.match(out[j - 1]):
        j -= 1
    return out[:j]


# ---------------------------------------------------------------------------------------------- Quran slice specs
def _base(s, a, w0, w1, sty):
    not_in_a(s, a)
    return {"surah": s, "ayah": a, "word_from": w0, "word_to": w1, "style": sty, "edit": None}


def _wrap(ts, words, trail, gold, kind, certainty, places, check=True, **extra):
    for p in (places if check else []):
        for a in range(p[1], p[2] + 1):
            not_in_a(p[0], a)
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
    styled = [style_word(x, sty) for x in ws[w0:w1]]
    return _wrap(_base(s, a, w0, w1, sty), styled, trail, [s, a, w1, min(w1 + nxt, len(ws))], ["continue"], "exact", [(s, a, a)])


def full(s, a, sty="dia", trail=""):
    """A whole ayah typed; nothing is left to add."""
    ws = W(s, a)
    pref = [fold_words(x)[0] for x in ws]
    assert occurrences(pref) == [(s, a, a)], ("complete verse sequence is not unique", s, a)
    return _wrap(_base(s, a, 0, len(ws), sty), [style_word(x, sty) for x in ws], trail, None, [], None, [(s, a, a)])


def part(s, a, n, chars, w0=0, sty="dia"):
    """n whole words, then the first `chars` letters of the next word (the caret is inside that word)."""
    ws = W(s, a)
    i = w0 + n
    word = strip(ws[i])
    assert 2 <= chars < len(word), (s, a, i, word, chars)
    plain_part = word[:chars]
    pf = fold_words(plain_part)
    assert len(pf) == 1
    typed_part = vocalised_cut(ws[i], chars) if sty == "dia" else plain_part
    assert fold_words(typed_part) == pf, (typed_part, plain_part)
    pref = [fold_words(x)[0] for x in ws[w0:i]]
    places = occurrences(pref + [pf[0]], last_prefix=True)
    assert places == [(s, a, a)], ("partial-word prefix is not unique", s, a, n, places)
    ts = _base(s, a, w0, i, sty)
    ts["edit"] = {"type": "partial", "word_index": i, "letters": chars}
    return _wrap(ts, [style_word(x, sty) for x in ws[w0:i]] + [typed_part], "", [s, a, i, i + 1], ["complete_word"], "exact", [(s, a, a)])


def wrong(s, a, n, bad, w0=0, sty="dia"):
    """n correct words, then a wrong word (and a space): the proposal replaces it with the verse word."""
    ws = W(s, a)
    i = w0 + n
    pref = [fold_words(x)[0] for x in ws[w0:i]]
    assert n >= 3 and occurrences(pref) == [(s, a, a)], ("replace prefix not distinctive", s, a, n, occurrences(pref))
    fb, fc = fold_words(bad), fold_words(ws[i])
    assert len(fb) == 1 and fb[0] != fc[0] and not fc[0].startswith(fb[0]) and not fb[0].startswith(fc[0]), (s, a, bad, ws[i])
    assert not occurrences(pref + fb), ("the wrong word is a real continuation somewhere", s, a, bad)
    if sty == "plain":
        assert strip(bad) == bad
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
    return _wrap(ts, [style_word(x, sty) for x in ws[w0:i]] + [style_word(ws[i + skip], sty)], " ", [s, a, i, i + skip], ["insert"],
                 "probable", [(s, a, a)], skipped=[strip(x) for x in ws[i:i + skip]])


def phr(s: int, a: int, text: str) -> tuple[int, int]:
    """(n words, index of its first word in the ayah) of the folded phrase `text` inside ayah (s, a)."""
    target = fold_words(text)
    f = [fold_words(x)[0] for x in W(s, a)]
    starts = [k for k in range(len(f) - len(target) + 1) if f[k:k + len(target)] == target]
    assert len(starts) == 1, (s, a, text, starts)
    return len(target), starts[0]


def amb(s, a, n, expect_places, w0=0, sty="dia", nxt=2):
    """Words shared by several verses; expect_places must be EXACTLY the places where the typed words occur."""
    ws = W(s, a)
    w1 = w0 + n
    pref = [fold_words(x)[0] for x in ws[w0:w1]]
    places = occurrences(pref)
    assert sorted(places) == sorted(expect_places), ("ambiguity places differ", s, a, n, sorted(places))
    assert len(places) > 1
    by_place = {}
    for (ps, pa, pb) in places:
        assert pa == pb
        not_in_a(ps, pa)
        pws = W(ps, pa)
        starts = [k for k in range(len(pws) - n + 1) if [fold_words(x)[0] for x in pws[k:k + n]] == pref]
        assert len(starts) == 1, (ps, pa, starts)
        k = starts[0] + n
        assert k < len(pws), ("an occurrence ends its ayah", ps, pa)
        by_place[f"{ps}:{pa}"] = [ps, pa, k, min(k + nxt, len(pws))]
    nexts = {fold_words(W(p[0], p[1])[by_place[f'{p[0]}:{p[1]}'][2]])[0] for p in places}
    return _wrap(_base(s, a, w0, w1, sty), [style_word(x, sty) for x in ws[w0:w1]], " ", None, ["continue"], "exact", sorted(places),
                 gold_words_by_place=by_place, distinct_continuations=len(nexts))


def slice_(s, a, w0, w1, sty="plain", trail=" "):
    """A Quran-looking stretch used in a negative case (no gold)."""
    ws = W(s, a)
    pref = [fold_words(x)[0] for x in ws[w0:w1]]
    assert occurrences(pref), (s, a)
    return _wrap(_base(s, a, w0, w1, sty), [style_word(x, sty) for x in ws[w0:w1]], trail, None, [], None, sorted(occurrences(pref)), check=False)


CASES: list[dict] = []


def ts_out(sp, role):
    return {**sp["ts"], "role": role}


def add(category, sp, *, pre="", cue=None, sep=": ", opener="", after="", close="", tail="", tail_sp=None, explicit=False, distinct=False,
        outcome=None, note, ok_status=("none",), none_acceptable=False, must_be_ambiguous=False, identical_continuation=False,
        cue_kind=None):
    """Compose a case. before = pre + cue + sep + opener + typed [+ close + tail (+ tail Quran-looking words)]."""
    head = pre + (cue + sep if cue else "") + opener
    typed = sp["typed"] if sp else ""
    before = head + typed + close + tail + (tail_sp["typed"] if tail_sp else "")
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
    if sp:
        role = "typed" if suggest or category in ("complete_verse", "cue_non_quran_hadith_dua_proverb") else "quoted_or_looking"
        specs.append(ts_out(sp, role))
    if tail_sp:
        specs.append(ts_out(tail_sp, "tail_looking"))
    CASES.append({
        "id": f"SG-{len(CASES) + 1:03d}", "category": category, "before": before, "after": after, "explicit": explicit, "distinct": distinct,
        "context": {"cue": cue, "cue_kind": cue_kind or ("quran" if cue else None), "opener": opener or None, "separator": sep if cue else None,
                    "close": close or None},
        "typed_specs": specs, "expect": exp,
    })


def add_none(category, text, *, after="", explicit=False, distinct=False, note, ok_status=("none",), tail_sp=None):
    """A none-case written wholly by hand (optionally ending in a Quran-looking stretch)."""
    before = text + (tail_sp["typed"] if tail_sp else "")
    CASES.append({
        "id": f"SG-{len(CASES) + 1:03d}", "category": category, "before": before, "after": after, "explicit": explicit, "distinct": distinct,
        "context": {"cue": None, "cue_kind": None, "opener": None, "separator": None, "close": None},
        "typed_specs": [ts_out(tail_sp, "tail_looking")] if tail_sp else [],
        "expect": {"outcome": "none", "kind": [], "certainty": None, "gold_places": [], "gold_words": None, "must_be_ambiguous": False,
                   "must_not_be_exact": False, "none_acceptable": False, "identical_continuation": False, "ok_status": list(ok_status), "note": note},
    })


# =================================================================================================== A. exact continuation after a Quran lead-in (22)
CA = "cue_continue"
N_A = "after an explicit Quran lead-in the typed words are an exact prefix of a single verse; the next words are an exact continuation"
add(CA, cont(5, 8, 9, sty="dia"), pre="وإذا احتدم الخلاف مع خصم فاذكر ميزان الإنصاف، ", cue="يقول ربنا في كتابه العزيز", sep="، ", opener="﴿",
    outcome="suggest", note=N_A + " (diacritized, 9 words; the lead-in is followed by several words before the verse)")
add(CA, cont(2, 286, 6, sty="plain"), pre="وتختم سورة البقرة بدعاء جامع يعلّمنا الله فيه كيف نسأله، ", cue="وفي القرآن الكريم", outcome="suggest",
    note=N_A + " (undiacritized; the shortest unique prefix is 6 words)")
add(CA, cont(28, 77, 4, sty="dia"), pre="وفي نصيحة قوم قارون له درس لكل ثريّ، ", cue="جاء في التنزيل", opener="﴿", outcome="suggest", note=N_A)
add(CA, cont(34, 28, 4, sty="plain"), pre="ورسالة النبي ﷺ ليست حكرًا على قومه، ", cue="قال سبحانه وتعالى", sep="، ", outcome="suggest",
    note=N_A + " (four words typed; the first three words occur in three surahs)")
add(CA, cont(50, 16, 4, sty="dia"), pre="ومن أعمق ما قيل في قرب الله من عباده، ", cue="قال عز وجل", opener="“", outcome="suggest",
    note=N_A + " (curly opening quote; the three-word opening is shared by three verses, four words are unique)")
add(CA, cont(41, 34, 4, sty="plain"), pre="وإذا أردت أن تتعلم فن التعامل مع المسيء فتأمل ما جاء هناك، ", cue="قال ربنا", sep=" في سورة فصلت: ",
    outcome="suggest", note=N_A + " (a longer separator after the lead-in)")
add(CA, cont(58, 11, 8, sty="dia"), pre="وآداب المجالس مما عُني به الوحي، ومنها ما ورد في سورة المجادلة، ", cue="قال الله تعالى", opener="﴿", after="﴾",
    outcome="suggest", note=N_A + "; the editor has already closed the bracket after the caret")
add(CA, cont(38, 29, 4, sty="dia"), pre="وغاية إنزال الكتاب أن يُتدبّر لا أن يُهجر، ", cue="يقول الله", opener="﴿", outcome="suggest", note=N_A)
add(CA, cont(95, 4, 5, sty="plain"), pre="وفي مطلع سورة التين قسم ثم جواب، ", cue="وفي التنزيل العزيز", outcome="suggest",
    note=N_A + "; only the last word of the verse remains (one-word continuation)")
add(CA, cont(12, 87, 6, sty="plain"), pre="ولا يزال الأمل مفتاح الفرج، ", cue="وقوله تعالى حكايةً عن يعقوب", outcome="suggest", note=N_A)
add(CA, cont(13, 11, 5, sty="dia"), pre="ومن سنن الله في التغيير أنه يبدأ من الداخل، ", cue="قال تعالى", sep=" في سورة الرعد: ", outcome="suggest", note=N_A)
add(CA, cont(16, 125, 3, sty="plain"), pre="وأصول الدعوة إلى الله لا تُنال بالعنف، ", cue="وجاء في كتاب الله", opener="﴿", outcome="suggest", note=N_A + " (three words)")
add(CA, cont(17, 36, 4, sty="dia"), pre="وأحذّر نفسي وإخواني من نشر الإشاعات، ", cue="قال الله تعالى محذّرًا من القول بلا علم", outcome="suggest",
    note=N_A + "; the lead-in is earlier in the same sentence, followed by an explanatory phrase")
add(CA, cont(3, 159, 5, sty="plain"), pre="ولعل أجمل ما وُصف به خُلق القائد الرحيم، ", cue="وقال تعالى", outcome="suggest", note=N_A)
add(CA, cont(25, 74, 6, sty="dia"), pre="ومن دعاء عباد الرحمن في أمر الأسرة، ", cue="وفي الذكر الحكيم", sep=" ", opener="﴿", outcome="suggest",
    note=N_A + " (lead-in «في الذكر الحكيم», space as separator)")
add(CA, cont(31, 18, 4, sty="plain"), pre="ومن وصايا لقمان لابنه (الوصية ٦ من ١٠)، ", cue="يقول الله تعالى", opener='"', outcome="suggest",
    note=N_A + " (Arabic-Indic digits in the prose; straight double quote)")
add(CA, cont(59, 18, 8, sty="dia"), pre="ومحاسبة النفس قبل يوم الحساب منهج قرآني، ", cue="قال الله تعالى", opener="﴿", outcome="suggest",
    note=N_A + "; the first seven words are the opening of verses in many surahs, the 8-word prefix is unique")
add(CA, cont(2, 274, 4, sty="plain"), pre="وفي باب الصدقة سرًّا وجهرًا وردت الآية ٢٧٤ من البقرة، ", cue="قال سبحانه", outcome="suggest",
    note=N_A + " (Arabic-Indic digits in the prose)")
N_U = "typed in Uthmani script as copied from a Quran app (alef-wasla, waw + dagger alef); same exact continuation expected"
add(CA, cont(62, 9, 7, sty="uth"), pre="وإذا سمعت نداء الجمعة فاترك ما بيدك، ", cue="قال الله تعالى", opener="﴿", outcome="suggest", note=N_U)
add(CA, cont(18, 46, 5, sty="uth"), pre="وهذه خاطرة قصيرة عن زينة الدنيا وزوالها، ", cue="في القرآن الكريم", outcome="suggest", note=N_U)
add(CA, cont(29, 45, 8, sty="uth"), pre="وأسلوب الوحي في وصف أثر الصلاة في النفس، ", cue="يقول ربنا", opener="﴿", outcome="suggest", note=N_U)
add(CA, cont(35, 29, 7, sty="uth"), pre="وهذه صفة التجار الذين يتاجرون مع الله، ", cue="قال تعالى", opener="“", outcome="suggest", note=N_U)

# =================================================================================================== B. continuation after an opening mark, no lead-in (12)
CB = "opener_continue"
N_B = "no lead-in words, but the typed words follow an opening quotation mark and are an exact prefix of a single verse"
add(CB, cont(7, 199, 3, sty="plain"), pre="وإذا فاجأك سوء خلق من أحد فهذا هو الدواء: ", opener="“", outcome="suggest", note=N_B + " (curly quote; three words)")
add(CB, cont(3, 133, 4, sty="dia"), pre="وللمسارعة إلى الخيرات منزلة عظيمة، فتأمل هذا النداء: ", opener="«", after="»", outcome="suggest",
    note=N_B + " («, closing guillemet already after the caret)")
add(CB, cont(6, 162, 5, sty="dia"), pre="أكتب في دفتر يومياتي كل صباح عبارة التسليم الكامل: ", opener="﴿", after="﴾", outcome="suggest", note=N_B + " (﴿)")
add(CB, cont(9, 119, 7, sty="plain"), pre="هذه آية حفظتها منذ الصغر وما زلت أرددها: ", opener='"', outcome="suggest",
    note=N_B + ' (straight double quote; seven words because the shorter openings are shared)')
add(CB, cont(10, 57, 6, sty="dia"), pre="ومن نعم الله على الناس كتاب فيه علاج الصدور: ", opener="﴿", outcome="suggest", note=N_B + " (﴿)")
add(CB, cont(11, 112, 3, sty="plain"), pre="وعن الاستقامة وعدم الطغيان يلخّص المربّون الأمر كله في: ", opener="“", outcome="suggest", note=N_B + " (curly quote)")
add(CB, cont(14, 40, 4, sty="dia"), pre="وفي مناجاة أبي الأنبياء لذريته ما يصلح أن يكون ورد كل أب، ", opener="«", outcome="suggest", note=N_B + " («)")
add(CB, cont(17, 70, 5, sty="plain"), pre="وهذه الكرامة الإنسانية التي جاءت بها الرسالة: ", opener="{", outcome="suggest", note=N_B + " (opening brace)")
add(CB, cont(19, 96, 6, sty="dia"), pre="وللمحبة بين الناس طريق إلهي واضح، ", opener="﴿", outcome="suggest", note=N_B + " (﴿)")
add(CB, cont(22, 77, 5, sty="plain"), pre="ومن أوجز ما أُمر به المؤمنون من العبادة والخير: ", opener="«", outcome="suggest", note=N_B + " («)")
add(CB, cont(39, 10, 5, sty="dia"), pre="وكلمة أخيرة للصابرين في بلاد الغربة: ", opener="“", outcome="suggest", note=N_B + " (curly quote)")
add(CB, cont(52, 21, 4, sty="plain"), pre="ومن لطائف فضل الله أن يجمع الأهل في الجنة، ", opener="﴿", outcome="suggest", note=N_B + " (﴿)")

# =================================================================================================== C. caret inside the last word (8)
CC = "partial_word"
N_C = "the caret is inside the last typed word, which is a prefix of the verse word; the word is to be completed (kind complete_word)"
add(CC, part(13, 11, 7, 3, w0=11, sty="plain"), pre="ومن أعظم قواعد التغيير الاجتماعي، ", cue="قال تعالى", opener="﴿", outcome="suggest",
    note=N_C + "; the typed letters «يغي» are also a prefix of the word «يغير» typed earlier in the same verse; the words start in mid-verse")
add(CC, part(65, 2, 4, 3, sty="dia"), pre="وفي آداب الفراق بالمعروف كلام كثير في هذه السورة، ", cue="قوله تعالى في سورة الطلاق", outcome="suggest",
    note=N_C + "; the same word «بمعروف» occurs twice in the verse; vocalized typing")
add(CC, part(3, 102, 7, 3, sty="plain"), pre="وأذكر أن شيخي كان يبدأ بها كل خطبة جمعة: ", opener="﴿", after="﴾", outcome="suggest",
    note=N_C + "; closing bracket after the caret")
add(CC, part(35, 10, 8, 2, sty="plain"), pre="ومن هنا نفهم أن العزة لا تُطلب من الخلق، ", cue="قال الله تعالى", outcome="suggest",
    note=N_C + "; only two letters typed")
add(CC, part(25, 74, 6, 3, sty="dia"), pre="ومن أجمل ما يدعو به الأزواج، ", cue="قال سبحانه", opener="“", after="\n", outcome="suggest",
    note=N_C + "; vocalized typing, a newline follows the caret")
add(CC, part(7, 31, 7, 2, sty="plain"), pre="وللزينة والنظافة عند الذهاب إلى بيوت الله مكانة في الشرع، ", cue="يقول ربنا", outcome="suggest", note=N_C + "; two letters typed")
add(CC, part(16, 125, 6, 4, sty="dia"), pre="وأدب الجدال مع المخالف مقرر في هذه الآية، ", opener="﴿", outcome="suggest", note=N_C + "; four letters, vocalized typing")
add(CC, part(3, 185, 5, 3, sty="plain"), pre="وأقرب موعظة في القرآن الكريم للقلب الغافل أن نتذكر ", cue="وقوله تعالى", sep=": ", outcome="suggest",
    note=N_C + "; the first four words open three verses in three surahs, the fifth word singles out one")

# =================================================================================================== D. wrong last word (replace) (14)
CD = "wrong_word_replace"
N_D = "a distinctive exact prefix, then a wrong word followed by a space: a PROBABLE correction (kind replace) of the wrong word to the verse word"
add(CD, wrong(28, 77, 3, "رَبَّكَ", sty="dia"), pre="وقد نصح الصالحون قارون بنصيحة تصلح لكل غني، ", cue="قال الله تعالى", opener="﴿",
    outcome="suggest", note=N_D + " (only three words typed before the wrong one; vocalized wrong word)")
add(CD, wrong(41, 34, 3, "أو", sty="plain"), pre="ولا أنسى هذه القاعدة الذهبية في معاملة الناس، ", cue="قوله تعالى", outcome="suggest",
    note=N_D + " (three words typed; a conjunction for another)")
add(CD, wrong(50, 16, 5, "له", sty="plain"), pre="وانظر إلى قرب الله من خلقه وعلمه بهم، ", cue="يقول ربنا", opener="﴿", outcome="suggest",
    note=N_D + " (a different pronoun)")
add(CD, wrong(61, 2, 5, "تفعلون", sty="dia"), pre="وهذا عتاب لمن يخالف قوله فعله، ", cue="قال الله تعالى", opener="﴿", outcome="suggest",
    note=N_D + " (the next verb of the verse in place of the right one: a transposition slip)")
add(CD, wrong(35, 29, 3, "آيات", sty="plain"), pre="وهذه تجارة لا خسارة فيها، ", cue="وفي القرآن الكريم", outcome="suggest",
    note=N_D + " (three words typed; a natural synonym-like slip)")
add(CD, wrong(12, 87, 3, "فاطلبوا", sty="dia"), pre="وفي كلمة يعقوب لبنيه عبرة في الأمل، ", cue="قال تعالى", opener="﴿", outcome="suggest",
    note=N_D + " (three words typed; a different imperative)")
add(CD, wrong(6, 162, 3, "وصيامي", sty="plain"), pre="وهي عبارة يرددها المسلم في استفتاح صلاته، ", cue="قوله تعالى", sep=": ", opener="﴿", outcome="suggest",
    note=N_D + " (three words typed; a plausible slip)")
add(CD, wrong(39, 10, 3, "الناس", sty="dia"), pre="وهو نداء رقيق من الرب لعباده المؤمنين، ", cue="يقول الله", outcome="suggest",
    note=N_D + " (three words typed; a different noun after «يا عباد»)")
add(CD, wrong(2, 263, 4, "عن", sty="plain"), pre="وفي أدب الصدقة والعطاء أن الكلمة الطيبة خير، ", cue="قال سبحانه", opener="﴿", outcome="suggest",
    note=N_D + " (a different preposition)")
add(CD, wrong(99, 7, 3, "حبة", sty="dia"), pre="وهذا ميزان العدل الدقيق يوم القيامة، ", cue="قال الله تعالى", outcome="suggest",
    note=N_D + " (a near-synonym of «ذرة»)")
add(CD, wrong(2, 185, 6, "نورا", sty="plain"), pre="ومن أجمل ما وُصف به شهر الصيام، ", cue="قال تعالى", opener="﴿", outcome="suggest",
    note=N_D + " (a different noun)")
add(CD, wrong(4, 29, 7, "بينهم", sty="dia"), pre="وفي باب المعاملات المالية قاعدة جامعة، ", cue="قال الله تعالى", opener="﴿", outcome="suggest",
    note=N_D + " (a long correct prefix, then a pronoun suffix changed)")
add(CD, wrong(53, 39, 5, "سعا", sty="plain"), pre="وللعمل والسعي في الحياة أصل ثابت، ", cue="وفي كتاب الله", outcome="suggest",
    note=N_D + " (a spelling slip of the verse word: alef for yaa)")
add(CD, wrong(95, 4, 5, "تقوم", sty="plain"), pre="ومن أجمل ما يُتلى في تكريم الإنسان، ", cue="وفي التنزيل", opener="﴿", outcome="suggest",
    note=N_D + " (a letter dropped from the verse word)")

# =================================================================================================== E. missing word (insert) (8)
CE = "missing_word_insert"
N_E = "a distinctive exact prefix, then the verse word that follows one or two omitted words (and a space): a PROBABLE insertion (kind insert) of the omitted words"
add(CE, miss(28, 77, 3, 1, sty="plain"), pre="وهذه وصية جامعة بين الدنيا والآخرة، ", cue="قال الله تعالى", opener="﴿", outcome="suggest", note=N_E + " (one word omitted)")
add(CE, miss(50, 16, 4, 1, sty="dia"), pre="ومن معاني الإحسان أن تستشعر قرب الله منك، ", cue="يقول ربنا", outcome="suggest", note=N_E + " (one word omitted)")
add(CE, miss(7, 31, 5, 2, sty="plain"), pre="وهذا أمر بالزينة عند الصلاة، ", cue="قوله تعالى", opener="﴿", outcome="suggest", note=N_E + " (two words omitted)")
add(CE, miss(65, 2, 4, 1, sty="dia"), pre="وفي أحكام الطلاق والرجعة ما يحفظ الحقوق، ", cue="قال سبحانه", outcome="suggest", note=N_E + " (one word omitted)")
add(CE, miss(4, 36, 3, 1, sty="plain"), pre="وأعظم حق على العبد حق خالقه، ", cue="جاء في كتاب الله", opener="﴿", outcome="suggest", note=N_E + " (one word omitted)")
add(CE, miss(2, 208, 5, 2, sty="dia"), pre="وهو نداء للمؤمنين إلى الاستسلام الشامل، ", cue="قال تعالى", outcome="suggest", note=N_E + " (two words omitted)")
add(CE, miss(17, 36, 4, 1, sty="plain"), pre="ومن أخلاق المؤمن التثبت قبل الكلام، ", cue="قال الله تعالى", opener="«", outcome="suggest", note=N_E + " (one word omitted)")
add(CE, miss(3, 159, 4, 1, sty="dia"), pre="وهو خطاب ملطّف للنبي ﷺ في شأن أصحابه، ", cue="يقول الله تعالى", opener="﴿", outcome="suggest", note=N_E + " (one word omitted)")

# =================================================================================================== F. ambiguous openings (10)
CF = "ambiguous_opening"
N_F = "the typed words begin several different verses; the answer must offer choices from different places or nothing — never one confident exact choice that picks a place arbitrarily"


def nexts_identical(sp):
    return sp["distinct_continuations"] == 1


def add_amb2(sp, extra="", **kw):
    add(CF, sp, outcome="suggest", must_be_ambiguous=True, none_acceptable=True, identical_continuation=nexts_identical(sp),
        note=N_F + f" ({len(sp['places'])} places{extra})", **kw)


add_amb2(amb(30, 60, 5, [(30, 60, 60), (40, 55, 55), (40, 77, 77)], sty="dia"), pre="والصبر على طول الطريق وعدٌ تكرر مرارًا، ", cue="يقول ربنا", opener="﴿",
         extra="; the five-word opening is the same in 3 verses, the following words differ")
add_amb2(amb(35, 10, 3, [(4, 134, 134), (11, 15, 15), (17, 18, 18), (35, 10, 10), (42, 20, 20)], sty="plain"), pre="وفي بيان وجهة الإنسان وطلبه، ", cue="قال الله تعالى",
         extra="; five verses, five different next words")
add_amb2(amb(15, 26, 3, [(15, 26, 26), (23, 12, 12), (50, 16, 16)], sty="dia"), pre="وأصل خلق الإنسان مذكور في أكثر من موضع، ", cue="وفي القرآن الكريم", opener="﴿")
add_amb2(amb(23, 2, 3, [(23, 2, 2), (51, 11, 11), (52, 12, 12)], sty="plain"), pre="وللناس مع الدين مواقف شتى، ", cue="قوله تعالى")
add_amb2(amb(15, 11, 3, [(15, 11, 11), (26, 5, 5), (43, 7, 7)], sty="dia"), pre="وكثيرًا ما تحدث القرآن عن موقف الأمم من رسلها، ", opener="﴿",
         extra="; no lead-in, only the opening mark")
add_amb2(amb(2, 210, 3, [(2, 210, 210), (6, 158, 158), (7, 53, 53), (16, 33, 33), (43, 66, 66)], sty="plain"), pre="وحال المكذبين في انتظار العذاب مذكور مرارًا، ",
         cue="جاء في كتاب الله", extra="; five verses with the same three-word opening")
add_amb2(amb(18, 110, 3, [(18, 110, 110), (38, 65, 65), (41, 6, 6)], sty="dia"), pre="وهذا هو الخطاب الذي أُمر النبي ﷺ أن يبلغه للناس، ", opener="«",
         extra="; guillemet opener")
add_amb2(amb(2, 176, 3, [(2, 176, 176), (8, 53, 53), (22, 6, 6), (22, 61, 61), (22, 62, 62), (31, 30, 30), (47, 11, 11)], sty="plain"),
         pre="وتعليل الأحكام الإلهية بالأسباب أسلوب متكرر، ", cue="قال سبحانه", extra="; seven verses, a very common opening of explanations")
add_amb2(amb(29, 61, 3, [(29, 61, 61), (29, 63, 63), (31, 25, 25), (39, 38, 38), (43, 9, 9), (43, 87, 87)], sty="dia"),
         pre="وإقرار المشركين بالخالق حجة عليهم، ", cue="يقول الله", extra="; six verses in four surahs")
add_amb2(amb(88, 1, 3, [(51, 24, 24), (79, 15, 15), (85, 17, 17), (88, 1, 1)], sty="plain"), pre="وأسلوب التشويق في القصص القرآني له وجوه، ",
         cue="قال الله عز وجل", opener="﴿", extra="; four verses, each followed by a different story")

# =================================================================================================== G. repeated / near-repeated verses (4)
CG = "repeated_verses"
N_G = "the same words occur at many places"
add(CG, amb(26, 9, 3, [(26, 9, 9), (26, 68, 68), (26, 104, 104), (26, 122, 122), (26, 140, 140), (26, 159, 159), (26, 175, 175), (26, 191, 191)], sty="dia"),
    pre="وتتكرر في سورة الشعراء خاتمة واحدة بعد كل قصة، ", cue="قال تعالى", opener="﴿", outcome="suggest", must_be_ambiguous=True,
    none_acceptable=True, identical_continuation=True, note=N_G + ": the refrain closing eight stories of surah 26; the continuation is identical at every place but the verse is not determined")
add(CG, amb(54, 17, 3, [(54, 17, 17), (54, 22, 22), (54, 32, 32), (54, 40, 40)], sty="plain"),
    pre="ومن أجمل ما كُرر في القرآن وعدٌ بتيسير حفظه، ", cue="قال سبحانه", outcome="suggest", must_be_ambiguous=True, none_acceptable=True,
    identical_continuation=True, note=N_G + ": the refrain of surah 54 (4 times); the continuation is identical everywhere")
add(CG, amb(7, 59, 8, [(7, 59, 59), (7, 65, 65), (7, 73, 73), (7, 85, 85), (11, 50, 50), (11, 61, 61), (11, 84, 84), (23, 23, 23)], w0=phr(7, 59, "يا قوم اعبدوا الله ما لكم من إله")[1], sty="dia"),
    pre="ودعوة الأنبياء الأولى واحدة على اختلاف أقوامهم، ", cue="في القرآن الكريم", outcome="suggest", must_be_ambiguous=True, none_acceptable=True,
    identical_continuation=True, note=N_G + ": the first call of the prophets (8 verses in 3 surahs; the typed words start after the first word of the verse, the next word is the same everywhere)")
add(CG, amb(2, 20, 4, [(2, 20, 20), (2, 106, 106), (2, 109, 109), (2, 148, 148), (2, 259, 259), (3, 165, 165), (16, 77, 77), (22, 17, 17), (24, 45, 45),
                       (29, 20, 20), (35, 1, 1), (65, 12, 12)], w0=phr(2, 20, "إن الله على كل")[1], sty="plain"),
    pre="وهذه عبارة يتداولها الناس في كلامهم كثيرًا، وهي كذلك ختام لكثير من الآيات، ", cue="قوله تعالى", outcome="suggest", must_be_ambiguous=True,
    none_acceptable=True, identical_continuation=True, note=N_G + ": a phrase common in everyday speech and found in 12 verses; the next word is the same but the words after it differ")

# =================================================================================================== H. complete verse (4)
CH = "complete_verse"
N_H = "the whole verse is already written; nothing is left to add"
add(CH, full(23, 1, "dia", trail=""), pre="وأول ما نزل من صفات الفلاح في هذه السورة قوله: ", cue="قال تعالى", sep=" ", opener="﴿", close="﴾", outcome="none", note=N_H + " (closing bracket typed)")
add(CH, full(87, 14, "plain", trail=" "), pre="وهي بشارة لمن زكّى نفسه، ", cue="يقول الله تعالى", outcome="none", note=N_H + " (a trailing space after the last word)")
add(CH, full(109, 6, "dia", trail=""), pre="وبهذه الآية تختم السورة، ", cue="وفي القرآن الكريم", opener="«", after="»", outcome="none", note=N_H)
add(CH, full(53, 39, "plain", trail=""), pre="ومن أصول السعي في الحياة ", cue="قال سبحانه", opener="“", outcome="none", note=N_H + " (a six-word verse)")

# =================================================================================================== I. hadith / du'a / proverb cue before Quran-looking words (8)
CI = "cue_non_quran_hadith_dua_proverb"
N_I = "the cue is a hadith / du'a / proverb cue, not a Quran lead-in: Quran-looking words after it must not be completed"
add(CI, cont(66, 6, 5, sty="plain"), pre="وفي خطبة الجمعة الماضية وقف الخطيب وذكّرنا، ثم ", cue="قال رسول الله ﷺ", sep=" لأصحابه: ", cue_kind="hadith", outcome="none",
    note=N_I + " (hadith cue)")
add(CI, cont(4, 1, 6, sty="dia"), pre="وروى أبو داود في سننه عن أحد الصحابة، ", cue="قال النبي ﷺ", cue_kind="hadith", outcome="none", note=N_I + " (hadith cue «قال النبي»)")
add(CI, cont(2, 208, 5, sty="plain"), pre="وقد ورد في السنة ما يوضح هذا المعنى، ", cue="وفي الحديث الشريف", cue_kind="hadith", outcome="none", note=N_I + " (hadith cue)")
add(CI, cont(25, 74, 4, sty="plain"), pre="وكان جدي يختم صلاته بكلمات يرددها بصوت خافت، ", cue="اللهم", sep=" ", cue_kind="dua", outcome="none", note=N_I + " (du'a cue «اللهم»)")
add(CI, cont(14, 40, 3, sty="dia"), pre="وهذا مما يُحفظ للأبناء في آخر الصلاة، ", cue="ومن الأدعية المأثورة", cue_kind="dua", outcome="none", note=N_I + " (du'a cue «أدعية»)")
add(CI, cont(59, 10, 4, sty="plain"), pre="ويحفظ العامة هذه الجملة عن ظهر قلب، ", cue="وفي الدعاء", cue_kind="dua", outcome="none", note=N_I + " (du'a cue «الدعاء»)")
add(CI, cont(3, 185, 5, sty="plain"), pre="وتتناقل الألسن هذه الجملة في المآتم، ", cue="كما يقول المثل", cue_kind="proverb", outcome="none", note=N_I + " (proverb cue)")
add(CI, cont(36, 82, 4, sty="dia"), pre="وصارت عبارة يستخدمها الناس عند الحديث عن سرعة الأمر، ", cue="وهو مثل سائر", cue_kind="proverb", outcome="none", note=N_I + " (proverb cue)")

# =================================================================================================== J. everyday formulas / ordinary prose without cue (16)
CJ = "everyday_no_cue"
N_J = "ordinary prose or an everyday formula with common Quran words, no Quran lead-in or opening mark, distinct=false: no suggestion"
J = [
    ("انتهى الاجتماع في الساعة ٩:٣٠ وقد أنجزنا كل البنود قبل الموعد، والحمد لله الذي هدانا لهذا",
     "ordinary prose ending in a seven-word Quran-looking tail («الحمد لله الذي هدانا لهذا»), with Arabic-Indic digits"),
    ("تلقينا نبأ وفاة جارنا أمس بعد مرض طويل، وكل نفس ذائقة",
     "condolence prose ending in «كل نفس ذائقة» with no lead-in"),
    ("وعليكم السلام ورحمة الله وبركاته، أبشر ما عليك أمر إن شاء الله، ولكن اكتب لي التفاصيل أولًا لأن",
     "chat-style reply with the greeting formula and «إن شاء الله»"),
    ("أعلنت الوزارة بدء التسجيل للفصل الدراسي الثاني ١٤٤٨هـ عبر المنصة الإلكترونية، وذكرت أن الذين",
     "news-style prose with Arabic-Indic digits ending in the very common word «الذين»"),
    ("اجتهد في عملك وتوكل على ربك ثم قل ربنا آتنا في الدنيا",
     "everyday advice ending in the supplication «ربنا آتنا في الدنيا» with no cue"),
    ("قررنا أن نؤجل الرحلة إلى الأسبوع القادم بسبب الأمطار، فإنما أمره إذا",
     "ordinary prose ending in a four-word Quran-looking tail"),
    ("فاتني القطار هذا الصباح فركضت إلى المحطة التالية، والله على ما أقول",
     "everyday oath formula in prose"),
    ("وعد المدير الموظفين بحوافز جديدة نهاية العام، ويا أيها الزملاء الأعزاء أرجو منكم أن",
     "office prose containing the vocative «يا أيها»"),
    ("السلام عليكم ورحمة الله وبركاته، أما بعد، فنفيدكم بأننا استلمنا طلبكم رقم ٤٥٧ وسنرد عليكم خلال ثلاثة أيام عمل، وإن الله مع",
     "business e-mail ending in «إن الله مع»"),
    ("كان جدي رحمه الله يحب الجلوس تحت النخلة بعد العصر ويروي لنا قصص شبابه، وكان يردد دائمًا ربنا لا",
     "family anecdote ending in the common opening «ربنا لا»"),
    ("سجل الفريق ثلاثة أهداف في الشوط الثاني وفاز بالكأس بعد غياب طويل، وفرح الجمهور فرحًا لا",
     "sports prose"),
    ("تبدأ الدورة التدريبية يوم الأحد القادم في القاعة الكبرى، ويستحسن الحضور قبل الموعد بنصف ساعة، وإنا لله",
     "notice ending in the condolence formula «إنا لله» with no cue"),
    ("أضف كوبين من الدقيق إلى الخليط وقلّب جيدًا، ثم ضع الصينية في الفرن وقل بسم الله",
     "recipe prose containing the basmala formula as an everyday habit"),
    ("ذَهَبَ الْوَلَدُ إِلَى الْمَدْرَسَةِ مُبَكِّرًا فَوَجَدَ الْبَابَ مُغْلَقًا فَقَالَ فِي نَفْسِهِ إِنَّ اللَّهَ مَعَ",
     "fully vocalized children's story ending in «إن الله مع»"),
    ("كتب لي أخي في الرسالة ٱلْحَمْدُ لِلَّهِ رَبِّ",
     "a pasted Uthmani-spelled formula inside a personal message, with no cue"),
    ("قال لي المدير غدًا نبدأ المشروع الجديد وعلينا أن نتوكل على الله وحده فهو حسبنا ونعم",
     "dialogue prose ending in «حسبنا ... ونعم»"),
]
assert len(J) == 16
for txt, n in J:
    add_none(CJ, txt, note=N_J + ": " + n)

# =================================================================================================== K. distinct=true, long exact prefix, no cue (6) + same without distinct (3)
CK = "distinct_long_prefix"
CK2 = "no_distinct_same_prefix"
N_K = "no cue and no opening mark, but distinct=true and the typed words are a long exact prefix of one verse: a continuation is expected"
K = [
    (cont(4, 1, 7, sty="plain"), "وجدت في رسالة قديمة من جدي هذه الجملة المنقولة: ", ""),
    (cont(33, 70, 7, sty="dia"), "وفي ختام الخطبة قرأ الإمام عبارة طويلة، وهذا نصها كما سجلته: ", "\n"),
    (cont(3, 102, 7, sty="plain"), "ولصقت على جدار المسجد ورقة كتب عليها: ", ""),
    (cont(2, 214, 8, sty="dia"), "ومما حفظته من أستاذي في الصف الثامن، وكنت أكتبه في دفتري: ", ""),
    (cont(49, 11, 7, sty="plain"), "وأرسل لي صديقي رسالة قصيرة نصها: ", " وانتهت الرسالة."),
    (cont(65, 2, 7, sty="dia"), "وعلى لوحة الإعلانات علّقوا ورقة مكتوبًا فيها: ", ""),
]
for sp, pre, aft in K:
    add(CK, sp, pre=pre, after=aft, distinct=True, outcome="suggest", note=N_K)
for (sp, pre, aft) in K[:3]:
    add(CK2, sp, pre=pre, after=aft, distinct=False, outcome="none",
        note="identical text to the matching distinct=true case, but without distinct and without any cue or opening mark: no suggestion")

# =================================================================================================== L. text after a closed bracket / full stop (5)
CL = "after_closed_quotation"
N_L = "the quotation or sentence is closed; the words typed afterwards are ordinary writing even though they look like the start of a verse"
add(CL, full(23, 1, "dia", trail=""), pre="وهذه أولى صفات الفلاح، ", cue="قال تعالى", opener="﴿", close="﴾", tail=". ثم ننتقل إلى الحديث عن الأخلاق، ومن ذلك ",
    tail_sp=slice_(31, 18, 0, 3, "plain"), outcome="none", note=N_L + " (bracket closed, then a new sentence)")
add(CL, full(109, 6, "dia", trail=""), pre="واختصر الموقف من الأديان كلها في جملة واحدة: ", opener="«", close="»", tail="، وهي كافية لمن تأمل، وللمعاملة الحسنة ميزان: ",
    tail_sp=slice_(41, 34, 0, 3, "plain"), outcome="none", note=N_L + " (guillemet closed)")
add(CL, slice_(99, 7, 0, 3, "plain", trail=" "), pre="كتبت عن الميزان والعدل في الأسبوع الماضي. ", cue="قال تعالى", sep=". ", outcome="none",
    note=N_L + " (the lead-in sentence is ended by a full stop before the Quran-looking words)")
add(CL, full(53, 39, "dia", trail=""), pre="وفي السعي والعمل يقول المؤمن لنفسه: ", cue="قال سبحانه", opener="“", close="”.", tail=" ثم يختم بالخلاصة وهي أن ",
    tail_sp=slice_(7, 199, 0, 3, "plain"), outcome="none", note=N_L + " (curly quotes closed, then a full stop)")
add(CL, slice_(87, 14, 0, 3, "dia", trail=""), pre="وللتزكية معنى عميق في القلب، ", cue="يقول الله تعالى", opener="﴿", close="﴾؟", tail=" نعم هذا هو، وبعد ذلك انتقل المحاضر إلى المحور الثاني، ",
    tail_sp=slice_(15, 99, 0, 2, "plain"), outcome="none", note=N_L + " (bracket and a question mark)")

# =================================================================================================== M. explicit=true, short but sufficient prefix (6) and one word (3)
CM = "explicit_short_prefix"
N_M = "explicit=true (the writer asked for a suggestion), no cue; two or three words that already single out one verse"
add(CM, cont(3, 159, 2, sty="plain"), pre="أحاول أن أتذكر بقية الآية التي تبدأ بـ ", explicit=True, outcome="suggest", note=N_M)
add(CM, cont(96, 1, 2, sty="dia"), pre="أكمل لي من فضلك: ", explicit=True, outcome="suggest", note=N_M + " (vocalized, two words)")
add(CM, cont(18, 46, 2, sty="plain"), pre="", explicit=True, outcome="suggest", note=N_M + " (nothing but the typed words)")
add(CM, cont(53, 39, 3, sty="plain"), pre="ما تمام هذا الموضع؟ ", explicit=True, outcome="suggest", note=N_M + " (three words)")
add(CM, cont(7, 199, 2, sty="dia"), pre="عبارة حفظتها صغيرًا وأريد إكمالها: ", explicit=True, outcome="suggest", note=N_M + " (vocalized)")
add(CM, cont(17, 36, 2, sty="plain"), pre="ساعدني في استحضار الباقي: ", explicit=True, outcome="suggest", note=N_M)
CM1 = "explicit_one_word"
N_M1 = "explicit=true but a single word: far too ambiguous to propose anything (none, or at most a hint asking for more words)"
for pre, w, ts in [("أكمل هذه العبارة: ", "فاصبر ", slice_(30, 60, 0, 1, "plain")),
                   ("", "ربنا ", slice_(2, 128, 0, 1, "plain")),
                   ("ماذا بعد هذه الكلمة؟ ", "ولقد ", slice_(23, 12, 0, 1, "plain"))]:
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
used = set()
for c in CASES:
    for t in c["typed_specs"]:
        used.add((t["surah"], t["ayah"]))
    for p in c["expect"]["gold_places"]:
        for a in range(p[1], p[2] + 1):
            used.add((p[0], a))
assert not (used & A_AYAHS), sorted(used & A_AYAHS)

ABOUT = (
    "Frozen evaluation set B for POST /api/suggest (verse suggestions computed ONLY from the Quranpedia Hafs text, no AI), written on "
    "3 October 2026 by an AI subagent (Claude) in a fresh context, as a second set independent of set A (eval/suggest_cases_20261003.json), under "
    "these blindness instructions: it was instructed NOT to read, grep or run app/suggest.py, app/static/suggest-ui.js, app/static/app.js, any test about "
    "suggestions or the /api/suggest endpoint, not to start the server and not to import app.suggest; it read only the contract (the `_about` and categories "
    "of set A, a few of its cases for the schema, the docstring and code of eval/validate_suggest_cases.py), the builder pattern (eval/build_suggest_cases.py) and the way to load the Quran text "
    "(only `from app.quran_source import source`); set A's JSON was also read by this builder to compute the set of set A's ayahs that must be avoided. "
    "The labels derive from the Quranpedia text and the written contract and NOT from observing what the implementation returns; the author cannot prove "
    "that it did not see the implementation (it can only say it was instructed not to and did not open those files). "
    "AUTHOR-WRITTEN (AI): NOT independent human-reviewed; the labels await review by a human Arabic / Quran specialist. The SHA-256 of this file is in "
    "eval/suggest_cases_b_20261003.sha256. No threshold or rule may be tuned against this file. "
    "Same schema, categories and category counts as set A (the shared validator requires them: 129 cases). The Arabic prose around the cues was written "
    "afresh (different lead-ins, openers and separators, Arabic-Indic digits, text after the caret, vocalized / unvocalized / Uthmani typing); harder cases than set A "
    "include wrong words after exactly three typed words, spelling slips, partial words that are also a full word elsewhere in the verse, repeated phrases found in "
    "several surahs (including one common in everyday speech), verses sharing a long prefix, and everyday text ending in a Quran-looking tail. "
    "Every ayah used here (typed, quoted, tail or gold) is disjoint from the ayahs used in set A (computed from set A's JSON when this file is built, and asserted). "
    "Only COORDINATES are stored for gold (gold_places = [surah, ayah_start, ayah_end]; gold_words = [surah, ayah, word_from, word_to) over the "
    "Quranpedia word list of that ayah); no Quran corpus is stored. The `before` strings necessarily contain the Quran words the writer is supposed to "
    "have typed (cut from the Quranpedia text by eval/build_suggest_cases_b_20261003.py by coordinates, as in set A); wrong / missing / partial-word variants are "
    "explicit edits (typed_specs[].edit) applied to those words. Labels are cross-checked by eval/validate_suggest_cases.py, which does not use the app's matching "
    "code. Contract encoded (as in set A): after an explicit Quran lead-in or an opening mark, >= 2 distinctive words -> the next words are an EXACT continuation "
    "(kind continue; complete_word when the caret is inside the last word); a distinctive prefix followed by a wrong word (then a space) -> PROBABLE replace, or "
    "PROBABLE insert when the typed word is the verse word after one or two skipped words; ambiguous or repeated openings -> several choices from different places "
    "(ambiguous=true) or nothing, never one confident exact choice; hadith / du'a / proverb cues, everyday formulas, text after a closed quotation or sentence, "
    "text with no cue/opener (distinct=false), complete verses and a single word -> none (a hint is also accepted only for the explicit one-word cases). "
    "Cases with none_acceptable=true (ambiguous, repeated) may also legitimately return none. expect fields: outcome (suggest|none); kind = acceptable kinds of "
    "the best choice; certainty = expected certainty of the best choice; gold_places = places that must be among the choices; gold_words = the Quran words that the "
    "proposed text must start with (for complete_word: the whole word, or its missing suffix); wrong_word/correct_word for replace; skipped_words for insert; "
    "ok_status = response statuses that are not a false suggestion."
)

data = {"_about": ABOUT, "version": 1, "written": "2026-10-03", "categories": dict(counts), "cases": CASES}
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"wrote {OUT.relative_to(ROOT)}: {len(CASES)} cases, {len(surahs)} surahs")
for k, v in counts.items():
    print(f"  {k}: {v}")
