"""Check eval/articles_long_20261003.json against the Quranpedia Hafs text, independently of the app's matching code.

    python eval/validate_articles_long_20261003.py [cases-file]     # default eval/articles_long_20261003.json ; exit 0 = labels OK

Same spirit as eval/validate_articles.py (own normalisation, own per-surah word streams; the source object is only used to READ
the text and the surah names/counts), extended for the long-article set:

  * gold "correct": the quote is a contiguous run of the Quran; "wording_error": it is not, yet differs from correct_text by a
    few words (<= 3 edit blocks, <= 4 words); correct_text occurs; ambiguous == (correct_text occurs in more than one place);
    the gold surah/ayah range is one of the places where correct_text occurs;
  * every gold quote occurs exactly once in the article, spans do not overlap; marked <=> the character before it is an opening
    mark (and the matching closing mark follows);
  * reference: parsed from reference_text (surah name or number, "S:A", "S:A-B", long form "سورة X، الآية N", Arabic-Indic digits);
    correct = names the gold place (or any place where correct_text occurs); incorrect = a valid but different place;
    out_of_range = ayah beyond the surah; surah_only = names the right surah only; missing = no reference text;
  * derived tags are recomputed from the text and must agree (marked/unmarked, plain/vocalized/uthmani, single/multi_verse,
    full_verse/partial/incomplete, short, missing_word/extra_word/one_word_wrong/wrong_first_word/wrong_last_word, numeric_ref,
    range_ref, long_form_ref, arabic_indic_digits, wrong_reference, repeated_in_quran); position tags inline_ref / ref_before /
    footnote_ref are checked against where the reference text sits; "repeated" needs another gold quotation of the same ayah;
  * negatives never occur contiguously in the Quran; formulas always do; all are substrings of the article;
  * set-level: 10 articles, each 7,000-19,000 characters (none over 19,500), total >= 100,000, at least 3 over 14,000,
    8-25 gold quotations each, real paragraph structure; the SHA-256 in articles_long_20261003.sha256 matches the file.
Reported (information): every run of >= 3 article words that occurs in the Quran OUTSIDE the gold quotations
(HARD-NEG = inside a labelled negative, formula = inside a formula, in-prose = unlabelled), and the kinds distribution.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.quran_source import source  # noqa: E402  (only used to obtain the source text)
from app.surahs import SURAHS  # noqa: E402  (names and verse counts only)

MARKS = re.compile(r"[ً-ٰٟۖ-ۭـ﻿]")
FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
OPEN = {"﴿": "﴾", "«": "»", '"': '"', "“": "”"}
LIMITS = dict(n_cases=10, min_chars=7000, max_chars=19000, hard_max=19500, total=100000, n_over_14k=3, min_gold=8, max_gold=25)
COUNTS = {n: c for n, _, c in SURAHS}


def fold(t: str) -> str:
    return " ".join(MARKS.sub("", t.replace("ٱ", "ا")).translate(FOLD).split())


NAMES = sorted(((fold(name), n) for n, name, _ in SURAHS), key=lambda x: -len(x[0]))


def words(t: str) -> list[str]:
    return re.sub(r"[^ء-ي ]", " ", MARKS.sub("", t.replace("ٱ", "ا"))).translate(FOLD).split()


def parse_ref(text: str):
    """-> ('ayah', surah, a0, a1) | ('surah', surah) | None"""
    t = text.translate(DIGITS).strip(" ()[]")
    m = re.match(r"^(\d+)\s*:\s*(\d+)(?:\s*[-–]\s*(\d+))?$", t)
    if m:
        return ("ayah", int(m.group(1)), int(m.group(2)), int(m.group(3) or m.group(2)))
    t = fold(t)
    t = re.sub(r"\bسوره\b|\bالايه\b|\bالايات\b|\bالايتان\b|\bايه\b|\bايات\b", " ", t)
    t = re.sub(r"[،:,()\[\]]", " ", t)
    t = " ".join(t.split())
    for name, n in NAMES:
        if t == name or t.startswith(name + " "):
            rest = [int(x) for x in re.findall(r"\d+", t[len(name):])]
            if not rest:
                return ("surah", n)
            return ("ayah", n, rest[0], rest[-1] if len(rest) > 1 else rest[0])
    return None


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "articles_long_20261003.json"
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    idx = source.get()
    streams: dict[int, list[tuple[str, int]]] = {}
    for (s, n), a in sorted(idx.ayahs.items()):
        for w in words(a.text):
            streams.setdefault(s, []).append((w, n))

    def find(ws: list[str]) -> list[tuple[int, int, int]]:
        out = []
        if not ws:
            return out
        for s, st in streams.items():
            fw = [w for w, _ in st]
            for i in range(len(fw) - len(ws) + 1):
                if fw[i:i + len(ws)] == ws:
                    out.append((s, st[i][1], st[i + len(ws) - 1][1]))
        return out

    problems: list[str] = []
    n_gold = n_neg = n_form = 0
    incidental: list[tuple[str, str, int, str]] = []
    kinds: Counter = Counter()
    refs: Counter = Counter()
    rows = []
    cases = data["cases"]
    total_chars = 0
    n_over = 0
    if len(cases) != LIMITS["n_cases"]:
        problems.append(f"expected {LIMITS['n_cases']} articles, found {len(cases)}")
    ids = [c["id"] for c in cases]
    if len(set(ids)) != len(ids):
        problems.append("duplicate case ids")
    for case in cases:
        art = case["article"]
        cid = case["id"]
        total_chars += len(art)
        n_over += len(art) > 14000
        if not LIMITS["min_chars"] <= len(art) <= LIMITS["max_chars"]:
            problems.append(f"{cid}: article is {len(art)} characters (allowed {LIMITS['min_chars']}-{LIMITS['max_chars']})")
        if len(art) > LIMITS["hard_max"]:
            problems.append(f"{cid}: over the hard maximum of {LIMITS['hard_max']} characters")
        paras = [p for p in art.split("\n\n") if p.strip()]
        if len(paras) < 8 or art != art.strip() or "\n\n\n" in art:
            problems.append(f"{cid}: paragraph structure ({len(paras)} paragraphs, or stray blank lines / edge whitespace)")
        if not LIMITS["min_gold"] <= len(case["gold"]) <= LIMITS["max_gold"]:
            problems.append(f"{cid}: {len(case['gold'])} gold quotations (allowed {LIMITS['min_gold']}-{LIMITS['max_gold']})")
        spans = []
        places = [(g["surah"], g["ayah_start"], g["ayah_end"]) for g in case["gold"]]
        for g in case["gold"]:
            n_gold += 1
            tag = f"{cid} «{g['quote'][:40]}»"
            tags = set(g["tags"])
            derived: set[str] = set()
            if art.count(g["quote"]) != 1:
                problems.append(f"{tag}: quote must occur exactly once in the article (occurs {art.count(g['quote'])})")
                continue
            p = art.index(g["quote"])
            q_end = p + len(g["quote"])
            spans.append((p, q_end))
            cw, qw = words(g["correct_text"]), words(g["quote"])
            locs = find(cw)
            if not locs:
                problems.append(f"{tag}: correct_text does not occur in the Quran")
            if g["ambiguous"] != (len(locs) > 1):
                problems.append(f"{tag}: ambiguous={g['ambiguous']} but correct_text occurs at {len(locs)} place(s)")
            if len(locs) > 1:
                derived.add("repeated_in_quran")
            gold_place = (g["surah"], g["ayah_start"], g["ayah_end"])
            if gold_place not in locs:
                problems.append(f"{tag}: gold location {gold_place} is not where correct_text occurs ({locs[:3]})")
            # --- wording
            ops = [o for o in SequenceMatcher(None, qw, cw, autojunk=False).get_opcodes() if o[0] != "equal"]
            if g["wording"] == "correct":
                if qw != cw:
                    problems.append(f"{tag}: labelled correct but differs from correct_text")
                if not find(qw):
                    problems.append(f"{tag}: labelled correct but does not occur in the Quran")
            elif g["wording"] == "wording_error":
                derived.add("wording_error")
                if find(qw):
                    problems.append(f"{tag}: labelled wording_error but the quote occurs in the Quran as written")
                if len(ops) > 3 or sum(max(o[2] - o[1], o[4] - o[3]) for o in ops) > 4:
                    problems.append(f"{tag}: not a slight misquotation ({len(ops)} edit blocks)")
                if len(ops) == 1:
                    op = ops[0]
                    if op[0] == "delete" and op[4] - op[3] == 0 and op[2] - op[1] == 1 or (op[0] == "insert" and op[4] - op[3] == 1):
                        derived.add("missing_word" if op[0] == "insert" else "extra_word")
                    if op[0] == "replace" and op[2] - op[1] == 1 and op[4] - op[3] == 1:
                        derived.add("one_word_wrong")
                for op in ops:
                    if op[3] == 0:
                        derived.add("wrong_first_word")
                    if op[4] == len(cw):
                        derived.add("wrong_last_word")
            else:
                problems.append(f"{tag}: unsupported wording label {g['wording']}")
            # --- marks
            before = art[p - 1:p] if p else ""
            marked = not g["unmarked"]
            derived.add("marked" if marked else "unmarked")
            if marked != (before in OPEN):
                problems.append(f"{tag}: unmarked={g['unmarked']} but the character before the quote is «{before}»")
            if marked and before in OPEN and art[q_end:q_end + 1] != OPEN[before]:
                problems.append(f"{tag}: opening mark {before} is not closed by {OPEN[before]}")
            # --- script form
            q = g["quote"]
            has_marks = bool(re.search("[ً-ْٰ]", q))
            if "ٱ" in q or re.search("[ۖ-ۭ]", q):
                derived.add("uthmani")
            elif has_marks:
                derived.add("vocalized")
            else:
                derived.add("plain")
            # --- extent
            derived.add("multi_verse" if g["ayah_end"] > g["ayah_start"] else "single_verse")
            full = " ".join(words(" ".join(idx.ayahs[(g["surah"], n)].text for n in range(g["ayah_start"], g["ayah_end"] + 1))))
            full_w = full.split()
            if cw == full_w:
                derived.add("full_verse")
            else:
                derived.add("partial")
                starts = [k for k in range(len(full_w) - len(cw) + 1) if full_w[k:k + len(cw)] == cw]
                if not starts:
                    problems.append(f"{tag}: correct_text is not inside the gold ayah range")
                elif starts[0] + len(cw) < len(full_w):
                    derived.add("incomplete")
            if len(cw) <= 4:
                derived.add("short")
            # --- reference
            rt = g["reference_text"]
            refs[g["reference"]] += 1
            if g["reference"] == "missing":
                derived.add("no_reference")
                if rt:
                    problems.append(f"{tag}: reference missing but reference_text is set")
            else:
                if not rt or art.count(rt) < 1:
                    problems.append(f"{tag}: reference_text «{rt}» is not present in the article")
                pr = parse_ref(rt or "")
                if pr is None:
                    problems.append(f"{tag}: reference_text «{rt}» is not a readable reference")
                else:
                    if g["reference"] == "surah_only":
                        if pr[0] != "surah" or pr[1] not in {l[0] for l in locs}:
                            problems.append(f"{tag}: surah_only reference «{rt}» does not name the gold surah")
                    elif pr[0] != "ayah":
                        problems.append(f"{tag}: reference «{rt}» names a surah only but is labelled {g['reference']}")
                    else:
                        named = (pr[1], pr[2], pr[3])
                        in_range = 1 <= pr[1] <= 114 and 1 <= pr[2] <= pr[3] <= COUNTS[pr[1]]
                        same = named == gold_place or named in locs
                        if g["reference"] == "correct" and not same:
                            problems.append(f"{tag}: reference labelled correct but names {named}")
                        if g["reference"] == "incorrect" and (same or not in_range):
                            problems.append(f"{tag}: reference labelled incorrect but names {named} (same={same}, in range={in_range})")
                        if g["reference"] == "out_of_range" and in_range:
                            problems.append(f"{tag}: reference labelled out_of_range but {named} is inside the surah")
                        if g["reference"] not in ("correct", "incorrect", "out_of_range"):
                            problems.append(f"{tag}: unsupported reference label {g['reference']}")
                if g["reference"] == "incorrect":
                    derived.add("wrong_reference")
                if re.match(r"^\s*[\d٠-٩]", rt or ""):
                    derived.add("numeric_ref")
                if re.search(r"[٠-٩]", rt or ""):
                    derived.add("arabic_indic_digits")
                if re.search(r"[\d٠-٩]\s*[-–]\s*[\d٠-٩]", rt or ""):
                    derived.add("range_ref")
                if re.search(r"سورة|الآية|الآيات|آية", rt or ""):
                    derived.add("long_form_ref")
                # where does it sit
                after = [m.start() for m in re.finditer(re.escape(rt or "§"), art) if m.start() >= q_end]
                bef = [m.start() for m in re.finditer(re.escape(rt or "§"), art) if m.end() <= p]
                if "inline_ref" in tags and not any(a - q_end <= 160 and "\n\n" not in art[q_end:a] for a in after):
                    problems.append(f"{tag}: tagged inline_ref but the reference does not follow the quote within 160 characters")
                if "ref_before" in tags and not any(p - (b + len(rt)) <= 160 and "\n\n" not in art[b:p] for b in bef):
                    problems.append(f"{tag}: tagged ref_before but the reference does not precede the quote within 160 characters")
                if "footnote_ref" in tags and not any("\n\n" in art[q_end:a] for a in after):
                    problems.append(f"{tag}: tagged footnote_ref but the reference is not in a later paragraph")
            if "repeated" in tags and sum(1 for pl in places if pl[0] == g["surah"] and pl[1] <= g["ayah_end"] and g["ayah_start"] <= pl[2]) < 2:
                problems.append(f"{tag}: tagged repeated but no other gold quotation cites the same ayah")
            # --- derived tags must all be present, and no unknown derived-type tag may be claimed
            for d in derived:
                if d not in tags:
                    problems.append(f"{tag}: derived tag «{d}» missing from tags")
            checkable = {"marked", "unmarked", "plain", "vocalized", "uthmani", "single_verse", "multi_verse", "full_verse", "partial",
                         "incomplete", "short", "missing_word", "extra_word", "one_word_wrong", "wrong_first_word", "wrong_last_word",
                         "numeric_ref", "range_ref", "long_form_ref", "arabic_indic_digits", "wrong_reference", "repeated_in_quran",
                         "no_reference", "wording_error"}
            for t in tags & checkable:
                if t not in derived:
                    problems.append(f"{tag}: tag «{t}» is claimed but not derivable from the text")
            kinds.update(tags)
        spans.sort()
        for a, b in zip(spans, spans[1:]):
            if b[0] < a[1]:
                problems.append(f"{cid}: gold quotations overlap")
        neg_spans = []
        for neg in case["negatives"]:
            n_neg += 1
            if neg not in art:
                problems.append(f"{cid}: negative «{neg}» not in article")
            else:
                s0 = art.index(neg)
                neg_spans.append((s0, s0 + len(neg)))
                if any(s0 < b and a < s0 + len(neg) for a, b in spans):
                    problems.append(f"{cid}: negative «{neg}» overlaps a gold quotation")
            if find(words(neg)):
                problems.append(f"{cid}: negative «{neg}» occurs in the Quran")
        form_spans = []
        for f in case.get("formulas", []):
            n_form += 1
            if f not in art:
                problems.append(f"{cid}: formula «{f}» not in article")
            else:
                s0 = art.index(f)
                form_spans.append((s0, s0 + len(f)))
            if not find(words(f)):
                problems.append(f"{cid}: formula «{f}» does not occur in the Quran (it should)")
        toks = [(m.start(), m.end(), words(m.group(0))) for m in re.finditer(r"[ء-ْٰـٱ]+", art)]
        toks = [(s, e, w[0]) for s, e, w in toks if w]
        i = 0
        while i < len(toks):
            j = i + 1
            best = 0
            while j <= len(toks) and (j == i + 1 or not art[toks[j - 2][1]:toks[j - 1][0]].strip()) and find([t[2] for t in toks[i:j]]):
                best = j
                j += 1
            if best - i >= 3:
                s0, e0 = toks[i][0], toks[best - 1][1]
                if not any(a <= s0 and e0 <= b for a, b in spans):
                    where = ("HARD-NEG" if any(a <= s0 and e0 <= b for a, b in neg_spans) else
                             "formula" if any(a <= s0 and e0 <= b for a, b in form_spans) else "in-prose")
                    incidental.append((cid, art[s0:e0], best - i, where))
                i = best
            else:
                i += 1
        rows.append((cid, len(art), len(paras), len(case["gold"]), len(case["negatives"]), len(case.get("formulas", []))))
    if total_chars < LIMITS["total"]:
        problems.append(f"total {total_chars} characters (need >= {LIMITS['total']})")
    if n_over < LIMITS["n_over_14k"]:
        problems.append(f"only {n_over} articles over 14,000 characters (need >= {LIMITS['n_over_14k']})")
    sha = path.with_suffix(".sha256")
    if path.name == "articles_long_20261003.json":
        if not sha.exists():
            print("note: articles_long_20261003.sha256 not found (create it after freezing)")
        else:
            want = sha.read_text().split()[0]
            if want != hashlib.sha256(raw).hexdigest():
                problems.append(f"SHA-256 mismatch: {sha.name} says {want}, the file hashes to {hashlib.sha256(raw).hexdigest()}")
    print(f"cases={len(cases)} gold={n_gold} negatives={n_neg} formulas={n_form} total_chars={total_chars} over_14k={n_over}")
    for cid, n, npar, ng, nn, nf in rows:
        print(f"  {cid}: {n} chars, {npar} paragraphs, {ng} gold, {nn} negatives, {nf} formulas")
    print("reference labels:", dict(refs))
    print("tag counts:", dict(sorted(kinds.items())))
    where_count = Counter(w for *_, w in incidental)
    print(f"incidental >=3-word Quran runs outside gold quotations: {len(incidental)} {dict(where_count)}")
    for c, run, n, where in incidental:
        print(f"  {where} {c}: «{run}» ({n} words)")
    for p in problems:
        print("PROBLEM:", p)
    print("labels OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
