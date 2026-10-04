"""Check eval/hard_quotes_dev_20261004.json and eval/hard_quotes_heldout_20261004.json against the cached Quranpedia Hafs text.

    .venv/bin/python eval/validate_hard_quotes_20261004.py [--report-runs] [dev.json heldout.json]
    exit 0 and "labels OK" only if every check passes.

Independent of the app's matching code and of the builder: it reads the cached Quranpedia JSON itself (path from HQ_SOURCE or
<tempdir>/quran-auditor-cache/hafs-mushaf-1.json) and uses app/surahs.py only for surah names and verse counts.

NORMALISATION (own): remove the Arabic diacritics U+064B-U+065F, the dagger alef U+0670, the Quranic annotation marks
U+06D6-U+06ED (including the small high sukun used in Uthmani-style text), tatweel U+0640, BOM and zero-width joiners; write
every alef form (آ أ إ ٱ ٲ ٳ) as ا, alef maqsura ى as ي, ta marbuta ة as ه, hamza on waw ؤ as و and hamza on ya ئ as ي;
then split into words on every character that is not an Arabic letter (U+0621-U+064A). Two texts "fold equal" when their
word lists are identical. A run "occurs in the Quran" when its folded words appear contiguously inside one surah (it may
cross an ayah boundary).

CHECKS: every correct_text equals the folded Quranpedia words at (surah, ayah_start..ayah_end, word_start..word_end); a quote
labelled correct folds equal to correct_text, a misquotation does not and does not occur anywhere in the Quran; the recorded
edits (error_detail) applied to the correct words reproduce the quote, and error agrees with them; quote == article[start:end];
the gold place is one of the places where correct_text occurs and ambiguous is true iff there are 2+ places; partial,
unmarked, context, lead_in_text, tags and expect follow the rules in the files' _about; the reference label agrees with the
written reference (correct = names a place where correct_text occurs, incorrect = a valid different ayah, out_of_range = an
ayah beyond the surah, surah_only = names the right surah only, missing = none); the quotation does not silently continue
into the neighbouring prose (the word just outside each end, when separated by spaces only, is not the next Quran word);
negatives sit at start/end, and unless kind == hard_negative they share no run of 3+ folded words with the Quran (a hard
negative records its longest shared run in shares_quran_run); negatives == the texts of negatives_detail; formulas occur in
the Quran; no unlabelled run of 3+ article words that occurs in the Quran remains in the prose (--report-runs lists them all,
including those inside hard negatives and formulas); short articles are 150-700 characters, long ones 2,500-6,000 with 6-12
quotations, a repeated quotation, an ambiguous phrase, a wrong-ayah reference, a footnote reference and 3+ negatives; the
gold ayahs of the two splits are disjoint and avoid the gold ayahs of eval/cases.json, heldout.json, phrases_frozen.json,
articles_frozen.json, articles_long_20261003.json; set-level counts (>= 90 positives in short articles, >= 60 negatives);
and the SHA-256 files, when present, match.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from app.surahs import SURAHS  # noqa: E402  (names and verse counts only)

SOURCE = Path(os.environ.get("HQ_SOURCE", Path(tempfile.gettempdir()) / "quran-auditor-cache" / "hafs-mushaf-1.json"))
DROP = {c for r in ((0x064B, 0x065F), (0x0670, 0x0670), (0x06D6, 0x06ED), (0x0640, 0x0640), (0xFEFF, 0xFEFF), (0x200C, 0x200F))
        for c in range(r[0], r[1] + 1)}
MAP = {0x0622: "ا", 0x0623: "ا", 0x0625: "ا", 0x0671: "ا", 0x0672: "ا", 0x0673: "ا", 0x0649: "ي", 0x0629: "ه", 0x0624: "و",
       0x0626: "ي"}
TABLE = {c: None for c in DROP} | MAP
LEAD_INS = ["قال الله تعالى", "قال تعالى", "يقول الله عز وجل", "يقول الله تعالى", "في القرآن الكريم", "كما في قوله تعالى",
            "قوله تعالى", "قال سبحانه", "يقول سبحانه", "جاء في التنزيل", "في كتاب الله", "قول الحق سبحانه"]
OPEN = {"﴿": "﴾", "«": "»", '"': '"'}
COUNTS = {n: c for n, _, c in SURAHS}
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
EXISTING = ["cases.json", "heldout.json", "phrases_frozen.json", "articles_frozen.json", "articles_long_20261003.json"]
ERRORS = ("none", "substitution", "omission", "wrong_first", "wrong_last", "extra_word", "two_errors")
CONTEXTS = ("none", "lead_in", "reference_ayah", "reference_surah", "quotation_marks", "brackets", "uthmani", "footnote_ref")
NEG_KINDS = ("prose_lookalike", "hadith", "dua", "proverb", "common_phrase", "hard_negative")


def fw(text: str) -> list[str]:
    t = (text or "").translate(TABLE)
    return [w for w in re.split(r"[^ء-ي]+", t) if w]


def fj(text: str) -> str:
    return " ".join(fw(text))


# ------------------------------------------------------------------ source
AY: dict[tuple[int, int], list[str]] = {}
for a in json.loads(SOURCE.read_text(encoding="utf-8"))["ayahs"]:
    AY[(a["surah"], a["number"])] = [w for t in a["text"].split() for w in fw(t)]
SURAH_WORDS: dict[int, list[tuple[str, int]]] = {}
for (s, n), ws in sorted(AY.items()):
    SURAH_WORDS.setdefault(s, []).extend((w, n) for w in ws)
INDEX: dict[str, list[tuple[int, int]]] = {}
for s, st in SURAH_WORDS.items():
    for i, (w, _) in enumerate(st):
        INDEX.setdefault(w, []).append((s, i))
NAMES = sorted(((fj(name), n) for n, name, _ in SURAHS), key=lambda x: -len(x[0]))


def places(ws: list[str]) -> list[tuple[int, int, int]]:
    out = []
    for s, i in INDEX.get(ws[0], []) if ws else []:
        st = SURAH_WORDS[s]
        if i + len(ws) <= len(st) and all(st[i + k][0] == ws[k] for k in range(len(ws))):
            out.append((s, st[i][1], st[i + len(ws) - 1][1]))
    return out


def in_quran(ws: list[str]) -> bool:
    return bool(places(ws))


def longest_run(ws: list[str]) -> list[str]:
    best: list[str] = []
    for i in range(len(ws)):
        j = i + 1
        while j <= len(ws) and in_quran(ws[i:j]):
            j += 1
        if j - 1 - i > len(best):
            best = ws[i:j - 1]
    return best if len(best) >= 3 else []


def parse_ref(text: str):
    """-> ('ayah', surah, a0, a1) | ('surah', surah) | None"""
    t = (text or "").translate(DIGITS).strip(" ()[]")
    m = re.fullmatch(r"(\d+)\s*:\s*(\d+)(?:\s*[-–]\s*(\d+))?", t)
    if m:
        return ("ayah", int(m.group(1)), int(m.group(2)), int(m.group(3) or m.group(2)))
    nums = [int(x) for x in re.findall(r"\d+", t)]
    words = [w for w in fw(t) if w not in ("سوره", "الايه", "الايات", "ايه", "رقم")]
    name = " ".join(words)
    for folded, n in NAMES:
        if name == folded:
            if not nums:
                return ("surah", n)
            return ("ayah", n, nums[0], nums[-1])
    return None


def source_words(g) -> list[str]:
    s, a0, a1, w0, w1 = g["surah"], g["ayah_start"], g["ayah_end"], g["word_start"], g["word_end"]
    if a0 == a1:
        return AY[(s, a0)][w0:w1]
    out = AY[(s, a0)][w0:]
    for n in range(a0 + 1, a1):
        out += AY[(s, n)]
    return out + AY[(s, a1)][:w1]


def neighbour_source_word(g, side: int) -> str | None:
    """The Quran word just before (side=-1) or after (side=+1) the gold range, within the surah."""
    st = SURAH_WORDS[g["surah"]]
    first = next(i for i, (_, n) in enumerate(st) if n == g["ayah_start"]) + g["word_start"]
    last = next(i for i, (_, n) in enumerate(st) if n == g["ayah_end"]) + g["word_end"] - 1
    k = first - 1 if side < 0 else last + 1
    return st[k][0] if 0 <= k < len(st) else None


def apply_edits(cw: list[str], edits: list[dict]) -> list[str]:
    sub = {e["position"]: fj(e["written"]) for e in edits if e["op"] == "substitute"}
    omit = {e["position"] for e in edits if e["op"] == "omit"}
    ins = {e["position"]: fj(e["written"]) for e in edits if e["op"] == "insert"}
    out = []
    for i in range(len(cw) + 1):
        if i in ins:
            out += ins[i].split()
        if i < len(cw) and i not in omit:
            out += sub[i].split() if i in sub else [cw[i]]
    return out


def existing_gold() -> tuple[set, set]:
    ayahs, texts = set(), set()
    for f in EXISTING:
        p = HERE / f
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for c in d["cases"] if isinstance(d, dict) else d:
            for g in c.get("gold", []):
                texts.add(fj(g["correct_text"]))
                for n in range(g["ayah_start"], g["ayah_end"] + 1):
                    ayahs.add((g["surah"], n))
    return ayahs, texts


def check_file(path: Path, problems: list[str], report: bool, stats: dict):
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    split = "dev" if "_dev_" in path.name else "heldout"
    if set(data) != {"_about", "version", "cases"} or data["version"] != f"hard-quotes-{split}-20261004":
        problems.append(f"{path.name}: top-level keys/version")
    about = data["_about"]
    for must in ("AI subagent (Claude)", "NOT human-reviewed", "NOT independent", "run ONCE", "4 Oct 2026"):
        if must not in about:
            problems.append(f"{path.name}: _about does not say «{must}»")
    sha = path.with_suffix(".sha256")
    if sha.exists():
        want = sha.read_text().split()
        if want[0] != hashlib.sha256(raw).hexdigest() or want[1] != path.name:
            problems.append(f"{sha.name}: does not match {path.name}")
    ids = [c["id"] for c in data["cases"]]
    if len(set(ids)) != len(ids):
        problems.append(f"{path.name}: duplicate ids")
    gold_ayahs = set()
    for case in data["cases"]:
        cid, art = case["id"], case["article"]
        tagp = f"{split}/{cid}"
        if set(case) != {"id", "category", "article", "gold", "negatives", "negatives_detail", "formulas"}:
            problems.append(f"{tagp}: case keys {sorted(case)}")
        is_long = case["category"] == "long_article"
        n = len(art)
        if is_long and not 2500 <= n <= 6000:
            problems.append(f"{tagp}: long article is {n} characters (2,500-6,000)")
        if not is_long and not 150 <= n <= 700:
            problems.append(f"{tagp}: short article is {n} characters (150-700)")
        if art != art.strip() or "\n\n\n" in art:
            problems.append(f"{tagp}: stray whitespace")
        spans = []
        gplaces = [(g["surah"], g["ayah_start"], g["ayah_end"]) for g in case["gold"]]
        for g in case["gold"]:
            tag = f"{tagp} «{g['quote'][:30]}»"
            stats["gold"][split] += 1
            stats["error"][(split, g["error"])] += 1
            for c in g["context"]:
                stats["context"][(split, c)] += 1
            if not is_long:
                stats["short_pos"][split] += 1
            for k in range(g["ayah_start"], g["ayah_end"] + 1):
                gold_ayahs.add((g["surah"], k))
            s0, e0 = g["start"], g["end"]
            if art[s0:e0] != g["quote"]:
                problems.append(f"{tag}: article[start:end] is not the quote")
                continue
            spans.append((s0, e0))
            if art.count(g["quote"]) != 1:
                problems.append(f"{tag}: quote must occur exactly once in the article (run_eval locates quotes by text)")
            try:
                sw = source_words(g)
            except KeyError:
                problems.append(f"{tag}: coordinates outside the source")
                continue
            cw, qw = fw(g["correct_text"]), fw(g["quote"])
            if not sw or cw != sw:
                problems.append(f"{tag}: correct_text «{' '.join(cw)}» is not the source words «{' '.join(sw)}» at its coordinates")
            locs = places(cw)
            if (g["surah"], g["ayah_start"], g["ayah_end"]) not in locs:
                problems.append(f"{tag}: gold place not among the places of correct_text {locs[:4]}")
            if g["ambiguous"] != (len(locs) > 1):
                problems.append(f"{tag}: ambiguous={g['ambiguous']} but correct_text occurs {len(locs)} time(s)")
            full = []
            for k in range(g["ayah_start"], g["ayah_end"] + 1):
                full += AY[(g["surah"], k)]
            if g["partial"] != (cw != full):
                problems.append(f"{tag}: partial={g['partial']} disagrees with the source")
            # --- wording, edits
            err, det = g["error"], g["error_detail"]
            if err not in ERRORS:
                problems.append(f"{tag}: unknown error {err}")
                continue
            if err == "none":
                if g["wording"] != "correct" or det is not None or qw != cw:
                    problems.append(f"{tag}: error none needs wording correct, no detail and quote == correct_text (folded)")
            else:
                if g["wording"] != "wording_error":
                    problems.append(f"{tag}: error {err} needs wording wording_error")
                if qw == cw:
                    problems.append(f"{tag}: misquotation folds equal to correct_text")
                if in_quran(qw):
                    problems.append(f"{tag}: misquotation occurs in the Quran as written {places(qw)[:3]}")
                edits = det if isinstance(det, list) else [det]
                if err == "two_errors" and (not isinstance(det, list) or len(det) != 2):
                    problems.append(f"{tag}: two_errors needs a list of two edits")
                if err != "two_errors" and not isinstance(det, dict):
                    problems.append(f"{tag}: {err} needs one edit object")
                okshape = True
                for e in edits:
                    p = e.get("position")
                    if e.get("op") not in ("substitute", "omit", "insert") or not isinstance(p, int):
                        okshape = False
                        continue
                    if e["op"] == "omit" and e.get("written") is not None:
                        problems.append(f"{tag}: omission must have written null")
                    if e["op"] == "insert" and e.get("source") is not None:
                        problems.append(f"{tag}: insertion must have source null")
                    if e["op"] in ("substitute", "omit"):
                        if not 0 <= p < len(cw) or fj(e.get("source")) != cw[p]:
                            problems.append(f"{tag}: edit source «{e.get('source')}» is not correct word {p}")
                        if e["op"] == "substitute" and fj(e["written"]) == cw[p]:
                            problems.append(f"{tag}: substitution writes the same word")
                if not okshape:
                    problems.append(f"{tag}: malformed edit")
                    continue
                if apply_edits(cw, edits) != qw:
                    problems.append(f"{tag}: the recorded edits do not reproduce the quote")
                if len(edits) == 1:
                    e = edits[0]
                    want = ("wrong_first" if e["op"] == "substitute" and e["position"] == 0 else
                            "wrong_last" if e["op"] == "substitute" and e["position"] == len(cw) - 1 else
                            "substitution" if e["op"] == "substitute" else
                            "omission" if e["op"] == "omit" and 0 < e["position"] < len(cw) - 1 else
                            "extra_word" if e["op"] == "insert" else "?")
                    if want != err:
                        problems.append(f"{tag}: error {err} but the edit is {want}")
            # --- marks, script, context
            before = art[s0 - 1] if s0 else ""
            marked = before in OPEN and art[e0:e0 + 1] == OPEN[before]
            if g["unmarked"] == marked:
                problems.append(f"{tag}: unmarked={g['unmarked']} but the characters around it are «{before}» «{art[e0:e0 + 1]}»")
            ctx = set(g["context"])
            if not ctx <= set(CONTEXTS) or not ctx:
                problems.append(f"{tag}: bad context {g['context']}")
            want_ctx = set()
            if marked:
                want_ctx.add("brackets" if before == "﴿" else "quotation_marks")
            uth = "ٱ" in g["quote"] or "ۡ" in g["quote"]
            if uth:
                want_ctx.add("uthmani")
            lt = g["lead_in_text"]
            if lt is not None:
                o = s0 - (1 if marked else 0)
                if not any(l in lt for l in LEAD_INS) or lt not in art[max(0, o - 40):o]:
                    problems.append(f"{tag}: lead_in_text «{lt}» is not a lead-in ending within 40 characters before the quotation")
                want_ctx.add("lead_in")
            else:
                o = s0 - (1 if marked else 0)
                if any(l in art[max(0, o - 20):o] for l in LEAD_INS):
                    problems.append(f"{tag}: a lead-in sits right before the quotation but lead_in_text is null")
            ref, rt = g["reference"], g["reference_text"]
            if ref in ("correct", "incorrect", "out_of_range"):
                want_ctx.add("reference_ayah")
            if ref == "surah_only":
                want_ctx.add("reference_surah")
            if ref == "missing":
                if rt is not None:
                    problems.append(f"{tag}: reference missing but reference_text set")
            else:
                pr = parse_ref(rt)
                if rt is None or rt not in art:
                    problems.append(f"{tag}: reference_text «{rt}» not in the article")
                elif pr is None:
                    problems.append(f"{tag}: reference_text «{rt}» is not a readable reference")
                else:
                    if ref == "surah_only":
                        if pr[0] != "surah" or pr[1] not in {l[0] for l in locs}:
                            problems.append(f"{tag}: surah_only reference «{rt}» does not name the gold surah only")
                    elif pr[0] != "ayah":
                        problems.append(f"{tag}: «{rt}» names a surah only but is labelled {ref}")
                    else:
                        named = pr[1:]
                        in_range = 1 <= pr[1] <= 114 and 1 <= pr[2] <= pr[3] <= COUNTS[pr[1]]
                        same = named in locs
                        ok = {"correct": same, "incorrect": in_range and not same, "out_of_range": not in_range}.get(ref)
                        if not ok:
                            problems.append(f"{tag}: reference «{rt}» labelled {ref} (names {named}, in range {in_range}, right {same})")
                    near = [m.start() for m in re.finditer(re.escape(rt), art)]
                    inline = any((p >= e0 and p - e0 <= 200 and "\n" not in art[e0:p]) or
                                 (p < s0 and s0 - (p + len(rt)) <= 200 and "\n" not in art[p:s0]) for p in near)
                    foot = not inline and any(p > e0 and "\n" in art[e0:p] for p in near)
                    if foot:
                        want_ctx.add("footnote_ref")
                    elif not inline:
                        problems.append(f"{tag}: reference «{rt}» is neither near the quotation (same paragraph, 200 characters) nor a later footnote")
            if not want_ctx:
                want_ctx = {"none"}
            if ctx != want_ctx:
                problems.append(f"{tag}: context {sorted(ctx)} but the text gives {sorted(want_ctx)}")
            # --- span does not continue into prose
            m_before = re.search(r"([ء-ْٰٱۖ-ۭ]+)(\s+)$", art[:s0])
            if m_before and not marked:
                w = fw(m_before.group(1))
                if w and w[-1] == neighbour_source_word(g, -1) and g["error"] not in ("wrong_first",):
                    problems.append(f"{tag}: the prose word before the quote continues the verse («{w[-1]}»)")
            m_after = re.match(r"(\s+)([ء-ْٰٱۖ-ۭ]+)", art[e0:])
            if m_after and not marked:
                w = fw(m_after.group(2))
                if w and w[0] == neighbour_source_word(g, +1) and g["error"] not in ("wrong_last",):
                    problems.append(f"{tag}: the prose word after the quote continues the verse («{w[0]}»)")
            # --- expect
            ex = g["expect"]
            nw = len(cw)
            lead = lt is not None
            want_detect = "required" if (marked or lead or ref != "missing" or (nw >= 4 and not g["ambiguous"])) else "desirable"
            want_auto = ("allowed_if_span_and_verse_established"
                         if marked and (ref == "correct" or (lead and nw >= 6 and not g["ambiguous"])) else "forbidden")
            if set(ex) != {"detect", "max_wording", "auto_replacement", "gold_verse_listed"}:
                problems.append(f"{tag}: expect keys")
            if ex.get("detect") != want_detect:
                problems.append(f"{tag}: expect.detect {ex.get('detect')} (rule gives {want_detect})")
            if g["wording"] != "correct" and ex.get("max_wording") not in ("difference", "uncertain"):
                problems.append(f"{tag}: a misquotation may never be matched")
            if g["wording"] == "correct" and ex.get("max_wording") != "matched":
                problems.append(f"{tag}: a correct quotation has max_wording matched")
            if ex.get("auto_replacement") != want_auto:
                problems.append(f"{tag}: expect.auto_replacement {ex.get('auto_replacement')} (rule gives {want_auto})")
            if ex.get("gold_verse_listed") is not True:
                problems.append(f"{tag}: gold_verse_listed must be true")
            # --- tags
            t = {"marked" if marked else "unmarked",
                 "uthmani" if uth else "vocalized" if re.search("[ً-ْ]", g["quote"]) else "plain",
                 "multi_verse" if g["ayah_end"] > g["ayah_start"] else "single_verse",
                 "partial" if g["partial"] else "full_verse",
                 {"missing": "no_reference", "correct": "reference_correct", "incorrect": "wrong_reference",
                  "out_of_range": "out_of_range_reference", "surah_only": "surah_only_reference"}.get(ref, "?")}
            if nw <= 3:
                t.add("short")
            if err != "none":
                t |= {"wording_error", {"substitution": "one_word_wrong", "omission": "missing_word", "extra_word": "extra_word",
                                        "wrong_first": "wrong_first_word", "wrong_last": "wrong_last_word",
                                        "two_errors": "two_edits"}.get(err, "?")}
            if len(locs) > 1:
                t.add("repeated_in_quran")
            if sum(1 for p in gplaces if p[0] == g["surah"] and p[1] <= g["ayah_end"] and g["ayah_start"] <= p[2]) >= 2:
                t.add("repeated_in_article")
            if lead:
                t.add("lead_in")
            if "footnote_ref" in want_ctx:
                t.add("footnote_ref")
            if set(g["tags"]) != t:
                problems.append(f"{tag}: tags {sorted(g['tags'])} but derived {sorted(t)}")
        spans.sort()
        for a, b in zip(spans, spans[1:]):
            if b[0] < a[1]:
                problems.append(f"{tagp}: gold quotations overlap")
        # --- negatives
        neg_spans = []
        if case["negatives"] != [n["text"] for n in case["negatives_detail"]]:
            problems.append(f"{tagp}: negatives != texts of negatives_detail")
        for nd in case["negatives_detail"]:
            stats["neg"][(split, nd["kind"])] += 1
            if set(nd) != {"text", "start", "end", "kind", "shares_quran_run", "expect"} or nd["expect"] != "no_finding_or_possible_only":
                problems.append(f"{tagp}: negative fields «{nd.get('text')}»")
            if art[nd["start"]:nd["end"]] != nd["text"]:
                problems.append(f"{tagp}: negative «{nd['text']}» is not at start/end")
                continue
            neg_spans.append((nd["start"], nd["end"]))
            if any(nd["start"] < b and a < nd["end"] for a, b in spans):
                problems.append(f"{tagp}: negative «{nd['text']}» overlaps a gold quotation")
            run = longest_run(fw(nd["text"]))
            if nd["kind"] not in NEG_KINDS:
                problems.append(f"{tagp}: negative kind {nd['kind']}")
            if nd["kind"] == "hard_negative":
                if not run or nd["shares_quran_run"] != " ".join(run):
                    problems.append(f"{tagp}: hard negative «{nd['text']}» shares_quran_run {nd['shares_quran_run']} (longest run {run})")
            elif run or nd["shares_quran_run"] is not None:
                problems.append(f"{tagp}: negative «{nd['text']}» ({nd['kind']}) shares the Quran run «{' '.join(run)}»")
        form_spans = []
        for f in case["formulas"]:
            if f not in art or not in_quran(fw(f)):
                problems.append(f"{tagp}: formula «{f}» missing from the article or not Quran text")
            for m in re.finditer(re.escape(f), art):
                form_spans.append((m.start(), m.end()))
        # --- category-level
        if is_long:
            gs = case["gold"]
            if not 6 <= len(gs) <= 12:
                problems.append(f"{tagp}: {len(gs)} quotations (6-12)")
            texts = Counter(fj(g["correct_text"]) for g in gs)
            if not any(v >= 2 for v in texts.values()):
                problems.append(f"{tagp}: no quotation used twice")
            if not any(g["ambiguous"] for g in gs):
                problems.append(f"{tagp}: no phrase that occurs in several verses")
            if not any(g["reference"] in ("incorrect", "out_of_range") for g in gs):
                problems.append(f"{tagp}: no wrong-ayah reference")
            if not any("footnote_ref" in g["context"] for g in gs):
                problems.append(f"{tagp}: no footnote reference")
            if len(case["negatives"]) < 3:
                problems.append(f"{tagp}: fewer than 3 negatives")
            if not any(g["unmarked"] for g in gs) or all(g["unmarked"] for g in gs):
                problems.append(f"{tagp}: needs both marked and unmarked quotations")
            if not any(g["wording"] != "correct" for g in gs) or all(g["wording"] != "correct" for g in gs):
                problems.append(f"{tagp}: needs both correct and misquoted quotations")
        elif case["category"] != "negative" and len(case["gold"]) != 1:
            problems.append(f"{tagp}: a short positive case has exactly one quotation")
        elif case["category"] == "negative" and case["gold"]:
            problems.append(f"{tagp}: a negative case has no gold")
        # --- unlabelled Quran runs in the prose
        labelled = [(a, b, "gold") for a, b in spans] + [(a, b, "neg") for a, b in neg_spans] + [(a, b, "formula") for a, b in form_spans]
        toks = []
        for m in re.finditer(r"[ء-ْٰٱۖ-ۭـ]+", art):
            w = fw(m.group(0))
            if w:
                toks.append((m.start(), m.end(), w[0]))

        def zone(s, e):
            for a, b, k in labelled:
                if a <= s and e <= b:
                    return (a, b, k)
            return None

        i = 0
        while i < len(toks):
            j = i + 1
            while j < len(toks) and not art[toks[j - 1][1]:toks[j][0]].strip() and zone(*toks[j][:2]) == zone(*toks[i][:2]):
                j += 1
            seg = toks[i:j]  # a stretch of words separated by spaces only, inside one zone
            z = zone(*seg[0][:2])
            k = 0
            while k < len(seg):
                e = k + 1
                while e <= len(seg) and in_quran([x[2] for x in seg[k:e]]):
                    e += 1
                e -= 1
                if e - k >= 3:
                    run = art[seg[k][0]:seg[e - 1][1]]
                    kind = z[2] if z else "PROSE"
                    if kind != "gold":
                        stats["runs"].append((split, cid, kind, run))
                    if kind == "PROSE":
                        problems.append(f"{tagp}: unlabelled Quran run in the prose «{run}»")
                    k = e
                else:
                    k += 1
            i = j
        stats["cases"][(split, case["category"])] += 1
        stats["neg_total"][split] += len(case["negatives"])
    return gold_ayahs, data


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    report = "--report-runs" in sys.argv
    paths = [Path(a) for a in args] or [HERE / "hard_quotes_dev_20261004.json", HERE / "hard_quotes_heldout_20261004.json"]
    problems: list[str] = []
    stats = {k: Counter() for k in ("gold", "error", "context", "short_pos", "neg", "cases", "neg_total")}
    stats["runs"] = []
    ayah_sets = {}
    texts = {}
    for p in paths:
        ga, data = check_file(p, problems, report, stats)
        ayah_sets[p.name] = ga
        texts[p.name] = {fj(g["correct_text"]) for c in data["cases"] for g in c["gold"]}
    ex_ayahs, ex_texts = existing_gold()
    names = list(ayah_sets)
    if len(names) == 2:
        both = ayah_sets[names[0]] & ayah_sets[names[1]]
        if both:
            problems.append(f"gold ayahs shared by the two splits: {sorted(both)}")
        shared_text = texts[names[0]] & texts[names[1]]
        if shared_text:
            problems.append(f"correct_text shared by the two splits: {sorted(shared_text)}")
        if sum(stats["short_pos"].values()) < 90:
            problems.append(f"only {sum(stats['short_pos'].values())} positives in short articles (need >= 90)")
        if sum(stats["neg_total"].values()) < 60:
            problems.append(f"only {sum(stats['neg_total'].values())} negatives (need >= 60)")
        if stats["cases"][("dev", "long_article")] != 3 or stats["cases"][("heldout", "long_article")] != 2:
            problems.append("need 3 long articles in dev and 2 in held-out")
    for n, ga in ayah_sets.items():
        if ga & ex_ayahs:
            problems.append(f"{n}: gold ayahs also gold in the existing sets: {sorted(ga & ex_ayahs)}")
        if texts[n] & ex_texts:
            problems.append(f"{n}: correct_text identical to an existing set's: {sorted(texts[n] & ex_texts)}")
    for split in ("dev", "heldout"):
        print(f"[{split}] cases {sum(v for (s, _), v in stats['cases'].items() if s == split)} "
              f"{ {c: v for (s, c), v in sorted(stats['cases'].items()) if s == split} }")
        print(f"[{split}] gold {stats['gold'][split]} (short-article positives {stats['short_pos'][split]}), "
              f"negatives {stats['neg_total'][split]}")
        print(f"[{split}] errors { {e: v for (s, e), v in sorted(stats['error'].items()) if s == split} }")
        print(f"[{split}] context { {c: v for (s, c), v in sorted(stats['context'].items()) if s == split} }")
        print(f"[{split}] negative kinds { {k: v for (s, k), v in sorted(stats['neg'].items()) if s == split} }")
    tot = sum(stats["gold"].values()) + sum(stats["neg_total"].values())
    if tot:
        dev_share = (stats["gold"]["dev"] + stats["neg_total"]["dev"]) / tot
        print(f"dev share of items (gold + negatives): {dev_share:.0%}")
    kinds = Counter(k for *_, k, _ in stats["runs"])
    print(f"Quran runs of 3+ words outside gold quotations: {len(stats['runs'])} {dict(kinds)}")
    if report:
        for split, cid, kind, run in stats["runs"]:
            print(f"  {kind:8} {split}/{cid}: «{run}»")
    for p in problems:
        print("PROBLEM:", p)
    print("labels OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
