"""Check eval/suggest_cases_20261003.json against the Quranpedia Hafs text.

Independent of the app's matching code AND of eval/build_suggest_cases.py (its own character-level normalisation and its
own per-surah word streams); it only reads the source text:

    python eval/validate_suggest_cases.py [cases-file]     # default eval/suggest_cases_20261003.json

For every case it re-derives, from the stored coordinates (typed_specs) and edits, the words the writer is supposed to have
typed and checks:
  * the coordinates exist; the typed words (folded) are exactly the end of `before` (role "typed") or occur in it
    (roles "quoted_or_looking" / "tail_looking", the latter at the end);
  * continue: gold_words are the words that FOLLOW the typed prefix in the same ayah; the prefix occurs at exactly the
    gold place(s); one place unless the case is marked ambiguous;
  * complete_word: the typed last word is a strict prefix of the gold word and the preceding words are at the gold place only;
  * replace: only the last word differs, it is not a prefix of / equal to the verse word, and prefix + wrong word occurs
    nowhere in the Quran; wrong_word / correct_word match the stored strings;
  * insert: the typed last word is the verse word after `count` omitted words, the omitted words are skipped_words, and the
    typed sequence occurs nowhere in the Quran as written;
  * ambiguous / repeated: gold_places is EXACTLY the set of places where the typed words occur (and > 1); the stored words
    after each place are right; identical_continuation is true only if they are all the same;
  * complete verses: all words of the ayah are typed and nothing follows in the verse; the sequence occurs once;
  * cue context: a Quran lead-in category carries a Quran lead-in right before the typed text; hadith / du'a / proverb cases carry
    a hadith / du'a / proverb cue and no Quran lead-in; no-cue categories carry neither a lead-in nor an opening mark;
  * explicit / distinct flags match the category; distinct=false cases repeat a distinct=true case exactly;
  * <= 800 characters; ids sequential; >= 40 different surahs.
Reported (information): the length of the Quran-looking tail of every none-case.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.quran_source import source  # noqa: E402  (only used to obtain the source text)

# ------------------------------------------------------------------------------------------------ own normalisation
_ALEF_LIKE = {"أ", "إ", "آ", "ٱ"}
_REPL = {"ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"}


def fold(text: str) -> list[str]:
    """Folded words. Combining marks (harakat, shadda, sukun, dagger alef, Quranic signs) and tatweel are dropped,
    except that waw/ya + dagger alef (Uthmani long alef) becomes an alef; alef variants become a bare alef; ى->ي ة->ه ؤ->و ئ->ي."""
    chars: list[str] = []
    prev_letter = ""
    for ch in text:
        if ch == "ـ" or ch == "﻿":
            continue
        if ch == "ٰ":  # dagger alef: after a waw / ya it is the Uthmani way to write a long alef; elsewhere (also after ى) it adds no letter
            if prev_letter in ("و", "ي") and chars and chars[-1] == prev_letter:
                chars[-1] = "ا"
            continue
        if unicodedata.category(ch) == "Mn" or 0x06D6 <= ord(ch) <= 0x06ED:
            continue
        if ch in _ALEF_LIKE:
            ch = "ا"
        orig = ch
        ch = _REPL.get(ch, ch)
        if "ء" <= ch <= "ي":
            chars.append(ch)
            prev_letter = orig
        else:
            chars.append(" ")
            prev_letter = ""
    return "".join(chars).split()


def has_marks(w: str) -> bool:
    return any(unicodedata.category(c) == "Mn" for c in w)


def plain(w: str) -> str:
    return "".join(c for c in w if unicodedata.category(c) != "Mn" and c not in "ـ﻿")


# ------------------------------------------------------------------------------------------------ cue lists (own)
QURAN_LEAD = [r"قال\s+(الله|تعالى|سبحانه|ربنا)", r"قوله\s+تعالى", r"يقول\s+(الله|تعالى|ربنا)", r"في\s+القرآن", r"في\s+كتاب\s+الله",
              r"في\s+التنزيل", r"الذكر\s+الحكيم", r"وقال\s+تعالى", r"قال\s+عز\s+وجل"]
OPENERS = ["﴿", "«", '"', "“", "{"]
NON_QURAN_CUES = {"hadith": [r"قال\s+رسول\s+الله", r"قال\s+النبي", r"الحديث", r"عن\s+النبي"],
                  "dua": [r"اللهم", r"دعاء", r"الدعاء", r"أدعية"],
                  "proverb": [r"المثل", r"الحكمة\s+السائرة", r"مثل\s+سائر"]}

QURAN_CUE_CATS = {"cue_continue", "partial_word", "wrong_word_replace", "missing_word_insert", "ambiguous_opening", "repeated_verses", "complete_verse"}
NO_CUE_CATS = {"everyday_no_cue", "distinct_long_prefix", "no_distinct_same_prefix", "explicit_short_prefix", "explicit_one_word"}
EXPLICIT_CATS = {"explicit_short_prefix", "explicit_one_word"}
TARGET = {"cue_continue": 22, "opener_continue": 12, "partial_word": 8, "wrong_word_replace": 14, "missing_word_insert": 8, "ambiguous_opening": 10,
          "repeated_verses": 4, "complete_verse": 4, "cue_non_quran_hadith_dua_proverb": 8, "everyday_no_cue": 16, "distinct_long_prefix": 6,
          "no_distinct_same_prefix": 3, "after_closed_quotation": 5, "explicit_short_prefix": 6, "explicit_one_word": 3}


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "suggest_cases_20261003.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    idx = source.get()

    ayah_words: dict[tuple[int, int], list[str]] = {k: a.words for k, a in idx.ayahs.items()}
    folded_ayah: dict[tuple[int, int], list[str]] = {}
    stream: dict[int, list[tuple[str, int]]] = {}
    for (s, n), ws in sorted(ayah_words.items()):
        fw = []
        for w in ws:
            f = fold(w)
            assert len(f) == 1, (s, n, w)
            fw.append(f[0])
        folded_ayah[(s, n)] = fw
        stream.setdefault(s, []).extend((f, n) for f in fw)
    swords = {s: [w for w, _ in st] for s, st in stream.items()}

    def find(ws: list[str], last_prefix_only: bool = False) -> list[tuple[int, int, int]]:
        out = []
        k = len(ws)
        for s, fw in swords.items():
            for i in range(len(fw) - k + 1):
                head = fw[i:i + k - 1] if last_prefix_only else fw[i:i + k]
                if head != (ws[:k - 1] if last_prefix_only else ws):
                    continue
                if last_prefix_only and not fw[i + k - 1].startswith(ws[-1]):
                    continue
                out.append((s, stream[s][i][1], stream[s][i + k - 1][1]))
        return out

    problems: list[str] = []
    n_ud = sum(1 for ws in ayah_words.values() for w in ws if re.search("[وي][ً-ٟ]*ٰ", w))
    if n_ud:
        problems.append(f"{n_ud} source words carry waw/ya + dagger alef: the Uthmani rule would change source folding")

    def bad(cid: str, msg: str) -> None:
        problems.append(f"{cid}: {msg}")

    cases = data["cases"]
    ids = [c["id"] for c in cases]
    if ids != [f"SG-{i + 1:03d}" for i in range(len(cases))]:
        problems.append("ids are not SG-001.. in sequence")
    by_id = {c["id"]: c for c in cases}
    surahs: set[int] = set()
    cats: dict[str, int] = {}
    info_tails: list[tuple[str, int]] = []

    def expected_typed(ts: dict, cid: str):
        """Folded words the writer is supposed to have typed for this spec, plus the raw typed words."""
        s, a = ts["surah"], ts["ayah"]
        if (s, a) not in ayah_words:
            bad(cid, f"ayah {s}:{a} does not exist")
            return None
        ws = ayah_words[(s, a)]
        w0, w1 = ts["word_from"], ts["word_to"]
        if not (0 <= w0 <= w1 <= len(ws)):
            bad(cid, f"word range {w0}:{w1} outside ayah {s}:{a} ({len(ws)} words)")
            return None
        raw = list(ws[w0:w1])
        if ts["style"] == "plain":
            raw = [plain(x) for x in raw]
        elif ts["style"] == "uth":
            pass  # checked below by folding only
        edit = ts["edit"]
        exp = [folded_ayah[(s, a)][i] for i in range(w0, w1)]
        extra = []
        if edit:
            i = edit["word_index"]
            if i != w1 or i >= len(ws):
                bad(cid, f"edit word_index {i} must equal word_to {w1} and exist")
                return None
            if edit["type"] == "partial":
                part = plain(ws[i])[:edit["letters"]]
                extra = fold(part)
            elif edit["type"] == "replace":
                extra = fold(edit["wrong"])
            elif edit["type"] == "skip":
                if i + edit["count"] >= len(ws):
                    bad(cid, "skip runs past the ayah")
                    return None
                extra = [folded_ayah[(s, a)][i + edit["count"]]]
            else:
                bad(cid, f"unknown edit {edit['type']}")
                return None
        return exp, extra

    for c in cases:
        cid, cat, before = c["id"], c["category"], c["before"]
        cats[cat] = cats.get(cat, 0) + 1
        e, ctx = c["expect"], c["context"]
        if len(before) > 800:
            bad(cid, f"before is {len(before)} characters (limit 800)")
        if cat not in TARGET:
            bad(cid, f"unknown category {cat}")
        if c["explicit"] != (cat in EXPLICIT_CATS):
            bad(cid, f"explicit={c['explicit']} does not match category {cat}")
        if c["distinct"] != (cat == "distinct_long_prefix"):
            bad(cid, f"distinct={c['distinct']} does not match category {cat}")
        fb = fold(before)

        # ---- cue / opener context
        cue, kind_cue = ctx["cue"], ctx["cue_kind"]
        lead_hits = [p for p in QURAN_LEAD if re.search(p, before)]
        if cat in QURAN_CUE_CATS or cat == "opener_continue":
            if cat == "opener_continue":
                if cue or not ctx["opener"] or lead_hits:
                    bad(cid, "opener case must have an opening mark and no lead-in words")
            else:
                if cue:
                    if not any(re.search(p, cue) for p in QURAN_LEAD):
                        bad(cid, f"cue «{cue}» is not a Quran lead-in")
                elif not ctx["opener"] or lead_hits:
                    bad(cid, "no Quran lead-in and no opening mark")
            if cue and cue not in before:
                bad(cid, "cue not in before")
        if cat == "cue_non_quran_hadith_dua_proverb":
            pats = NON_QURAN_CUES.get(kind_cue or "", [])
            if not cue or not any(re.search(p, cue) for p in pats):
                bad(cid, f"cue «{cue}» is not a {kind_cue} cue")
            if lead_hits:
                bad(cid, f"a Quran lead-in is present in a non-Quran-cue case: {lead_hits}")
        if cat in NO_CUE_CATS:
            if lead_hits or any(o in before for o in OPENERS) or cue or ctx["opener"]:
                bad(cid, f"no-cue category but a lead-in/opening mark is present: {lead_hits}")
        if cat == "after_closed_quotation":
            if not e["outcome"] == "none":
                bad(cid, "closed-quotation case must be none")
            marks = [m for m in ("﴾", "»", '"', "؟", ".") if m in before]
            if not marks:
                bad(cid, "no closing mark or full stop in before")

        # ---- typed specs
        specs = c["typed_specs"]
        main = [t for t in specs if t["role"] == "typed"]
        for t in specs:
            surahs.add(t["surah"])
            r = expected_typed(t, cid)
            if r is None:
                continue
            exp, extra = r
            words = exp + extra
            if t["role"] in ("typed", "tail_looking"):
                # these stretches end the text
                if t["role"] == "tail_looking" or t is main[0]:
                    if fb[-len(words):] != words:
                        bad(cid, f"typed words {words} are not the end of before ({fb[-len(words):]})")
            else:
                joined = " ".join(fb)
                if " ".join(words) not in joined:
                    bad(cid, f"quoted words {words} do not occur in before")
            # style checks on the raw text
            if t["style"] == "plain" and t["role"] == "typed":
                n_typed = (t["word_to"] - t["word_from"]) + (1 if t["edit"] else 0)
                tail_text = " ".join(before.split()[-n_typed:])
                if has_marks(tail_text):
                    bad(cid, "style plain but the typed words carry diacritics")
            if t["style"] == "uth":
                if not re.search("[ٱ]|و[ً-ٟ]*ٰ", before):
                    bad(cid, "style uth but no Uthmani feature in before")
            if t["style"] == "dia" and t["role"] == "typed" and not t["edit"]:
                typed_raw = " ".join(ayah_words[(t["surah"], t["ayah"])][t["word_from"]:t["word_to"]])
                if typed_raw not in before:
                    bad(cid, "style dia but the diacritized source words are not in before verbatim")

        # ---- outcome checks
        if e["outcome"] == "none":
            if e["gold_places"] or e["gold_words"]:
                bad(cid, "none case carries gold")
            if not set(e["ok_status"]) <= {"none", "hint"} or "none" not in e["ok_status"]:
                bad(cid, f"bad ok_status {e['ok_status']}")
            if cat == "explicit_one_word" and sorted(e["ok_status"]) != ["hint", "none"]:
                bad(cid, "explicit one-word cases must accept none and hint")
            # information: how Quran-looking is the end of the text?
            best = 0
            for k in range(2, min(len(fb), 12) + 1):
                if find(fb[-k:]):
                    best = k
            info_tails.append((cid, best))
            if cat == "complete_verse":
                t = main[0] if main else None
                if not t or t["edit"] or t["word_from"] != 0 or t["word_to"] != len(ayah_words[(t["surah"], t["ayah"])]):
                    bad(cid, "complete_verse must type the whole ayah")
                elif find(folded_ayah[(t["surah"], t["ayah"])]) != [(t["surah"], t["ayah"], t["ayah"])]:
                    bad(cid, "the complete verse does not occur exactly once")
            if cat in ("cue_non_quran_hadith_dua_proverb", "after_closed_quotation", "explicit_one_word"):
                if cat != "after_closed_quotation" and not specs:
                    bad(cid, "expected a Quran-looking spec")
        elif e["outcome"] == "suggest":
            if len(main) != 1:
                bad(cid, "a suggest case needs exactly one `typed` spec")
                continue
            t = main[0]
            s, a = t["surah"], t["ayah"]
            ws = ayah_words[(s, a)]
            fa = folded_ayah[(s, a)]
            exp, extra = expected_typed(t, cid) or ([], [])
            edit = t["edit"]
            places = [tuple(p) for p in e["gold_places"]]
            for p in places:
                surahs.add(p[0])
            gw = e["gold_words"]
            kinds = e["kind"]
            if not edit:
                found = sorted(find(exp))
                if len(exp) < 2:
                    bad(cid, "fewer than two typed words in an exact continuation")
                if e["must_be_ambiguous"]:
                    if len(found) < 2:
                        bad(cid, f"marked ambiguous but the typed words occur at {len(found)} place(s)")
                    if sorted(places) != found:
                        bad(cid, f"gold_places differ from the places where the typed words occur ({len(places)} vs {len(found)})")
                    if kinds != ["continue"]:
                        bad(cid, "ambiguous case must have kind continue")
                    byp = e.get("gold_words_by_place", {})
                    nexts = set()
                    for (ps, pa, pb) in found:
                        pf = folded_ayah[(ps, pa)]
                        starts = [k for k in range(len(pf) - len(exp) + 1) if pf[k:k + len(exp)] == exp]
                        if len(starts) != 1:
                            bad(cid, f"typed words occur {len(starts)} times in {ps}:{pa}")
                            continue
                        k = starts[0] + len(exp)
                        if k >= len(pf):
                            bad(cid, f"typed words end the ayah {ps}:{pa}")
                            continue
                        if byp.get(f"{ps}:{pa}") != [ps, pa, k, min(k + 2, len(pf))]:
                            bad(cid, f"gold_words_by_place wrong at {ps}:{pa}: {byp.get(f'{ps}:{pa}')}")
                        nexts.add(pf[k])
                    if e["identical_continuation"] != (len(nexts) == 1):
                        bad(cid, f"identical_continuation={e['identical_continuation']} but there are {len(nexts)} distinct next words")
                    if not e["none_acceptable"]:
                        bad(cid, "ambiguous case must accept none")
                else:
                    if found != [(s, a, a)] or places != [(s, a, a)]:
                        bad(cid, f"typed words occur at {found}, gold_places {places}: must be exactly one place")
                    if kinds != ["continue"]:
                        bad(cid, f"kind {kinds} for an exact continuation")
                    if gw is None or gw[0] != s or gw[1] != a or gw[2] != t["word_to"] or gw[3] <= gw[2] or gw[3] > len(ws):
                        bad(cid, f"gold_words {gw} are not the continuation after word {t['word_to']}")
                    if e["certainty"] != "exact" or e["must_not_be_exact"]:
                        bad(cid, "exact continuation must expect certainty exact")
            else:
                i = edit["word_index"]
                typed = exp + extra
                if edit["type"] == "partial":
                    if kinds != ["complete_word"]:
                        bad(cid, f"kind {kinds} for a partial word")
                    word = fa[i]
                    if not (word.startswith(extra[0]) and extra[0] != word and len(extra[0]) >= 2):
                        bad(cid, "partial is not a strict prefix (>= 2 letters) of the verse word")
                    found = find(typed, last_prefix_only=True)
                    if found != [(s, a, a)] or places != [(s, a, a)]:
                        bad(cid, f"partial-word prefix occurs at {found}: must be exactly the gold place")
                    if gw != [s, a, i, i + 1]:
                        bad(cid, f"gold_words {gw} must be the completed word {i}")
                    if before.endswith(" "):
                        bad(cid, "partial-word case must not end with a space")
                elif edit["type"] == "replace":
                    if kinds != ["replace"] or e["certainty"] != "probable" or not e["must_not_be_exact"]:
                        bad(cid, "replace must be kind replace, probable, not exact")
                    wrong_f, right_f = extra[0], fa[i]
                    if wrong_f == right_f or right_f.startswith(wrong_f) or wrong_f.startswith(right_f):
                        bad(cid, "wrong word equals / is a prefix of / extends the verse word")
                    if len(exp) < 3 or find(exp) != [(s, a, a)]:
                        bad(cid, "replace prefix must be >= 3 words and unique")
                    if find(typed):
                        bad(cid, "prefix + wrong word occurs in the Quran")
                    if gw != [s, a, i, i + 1] or places != [(s, a, a)]:
                        bad(cid, "replace gold wrong")
                    if e.get("wrong_word") != edit["wrong"] or e.get("correct_word") != plain(ws[i]):
                        bad(cid, "wrong_word / correct_word do not match the edit and the verse")
                    if not before.endswith(edit["wrong"] + " "):
                        bad(cid, "replace case must end with the wrong word and a space")
                elif edit["type"] == "skip":
                    k = edit["count"]
                    if kinds != ["insert"] or e["certainty"] != "probable" or not e["must_not_be_exact"] or k not in (1, 2):
                        bad(cid, "insert must be kind insert, probable, skipping 1 or 2 words")
                    if len(exp) < 3 or find(exp) != [(s, a, a)]:
                        bad(cid, "insert prefix must be >= 3 words and unique")
                    if find(typed):
                        bad(cid, "the typed (gapped) sequence occurs in the Quran as written")
                    if gw != [s, a, i, i + k] or places != [(s, a, a)]:
                        bad(cid, "insert gold wrong")
                    if e.get("skipped_words") != [plain(x) for x in ws[i:i + k]]:
                        bad(cid, "skipped_words do not match the verse")
                    if not before.endswith(" "):
                        bad(cid, "insert case must end with a space")
        else:
            bad(cid, f"unknown outcome {e['outcome']}")

    # ---- paired distinct / no-distinct cases
    dist = [c for c in cases if c["category"] == "distinct_long_prefix"]
    for c in cases:
        if c["category"] == "no_distinct_same_prefix":
            if not any(d["before"] == c["before"] and d["after"] == c["after"] for d in dist):
                bad(c["id"], "no matching distinct=true case")
    for c in dist:
        t = c["typed_specs"][0]
        if t["word_to"] - t["word_from"] < 6:
            bad(c["id"], "distinct case needs a long prefix (>= 6 words)")
    if len(surahs) < 40:
        problems.append(f"only {len(surahs)} different surahs (need >= 40)")
    for k, v in TARGET.items():
        if cats.get(k) != v:
            problems.append(f"category {k}: {cats.get(k)} cases (target {v})")

    n_none = sum(1 for c in cases if c["expect"]["outcome"] == "none")
    print(f"cases={len(cases)} suggest={len(cases) - n_none} none={n_none} surahs={len(surahs)}")
    for k, v in cats.items():
        print(f"  {k}: {v}")
    looking = [(cid, n) for cid, n in info_tails if n >= 2]
    print(f"none-cases whose text ENDS in a >=2-word Quran sequence (hard negatives): {len(looking)} of {len(info_tails)}")
    for cid, n in looking:
        print(f"  {cid} ({by_id[cid]['category']}): last {n} words occur in the Quran")
    for p in problems:
        print("PROBLEM:", p)
    print("labels OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
