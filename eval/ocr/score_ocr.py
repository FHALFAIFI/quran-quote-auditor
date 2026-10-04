"""Score Arabic OCR output against typed ground truth (roadmap Stage 3.2). Nothing here reaches the app or the UI.

    python eval/ocr/score_ocr.py --manifest M.json --run RUN.json [--data-dir DIR] [--quran-cache PATH] [--out REPORT.json]

Inputs (format: eval/ocr/README.md, eval/ocr/manifest.schema.json):
  * a manifest: one record per page with its ground truth (inline or a file), its rights record and the character
    spans of Quran quotations in the ground truth (surah/ayah);
  * a run record: one engine's text per page, with the seconds and the cost the run itself recorded.

Reported, overall, per page and per page category / script / diacritics level (pooled counts, never means of rates):
  * CER, on the words joined by single spaces, with diacritics ("strict") and without them ("letters");
  * WER, strict and letters-level (each from its own word alignment);
  * WER inside Quran-quotation spans: the OCR words are aligned to the ground-truth words (letters-level Levenshtein
    alignment) and each span is projected through that alignment; an inserted OCR word counts inside a span when
    both of its neighbouring ground-truth words are in that span;
  * diacritic error rate: within aligned word pairs, base letters are aligned and their sets of marks compared; the
    rate is letters whose marks differ / letters where either side carries a mark;
  * "plausible wrong word": a substituted OCR word whose folded form differs from the truth's and is itself in a word
    list made at run time from the cached Quran text (if present) and the benchmark's own ground truth. This is an
    APPROXIMATION of "a valid Arabic word": the list is neither a dictionary nor complete, and it is reported as such;
  * time and cost per page, read from the run record only (never estimated here).

Punctuation, brackets (﴿ ﴾ « »), tatweel, zero-width characters and Quranic pause/annotation marks are not counted:
words are runs of letters, digits and diacritics. Arabic-Indic and ASCII digits compare equal.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import arabic  # noqa: E402
from app.surahs import AYAH_COUNTS  # noqa: E402

SCHEMA_VERSION = 1
CATEGORIES = {"newspaper", "bulletin", "book", "phone_photo", "screenshot", "other"}
SCRIPTS = {"naskh", "uthmani", "mixed", "other"}
DIACRITICS_LEVELS = {"none", "partial", "full"}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PAGE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_MARKS = "ؐ-ًؚ-ٰٟۖ-ۭـ‌‍"
_WORD = re.compile(rf"(?:[^\W_]|[{_MARKS}])+")


# --------------------------------------------------------------------------- words


@dataclass(frozen=True)
class Word:
    start: int  # offsets in the original text (end exclusive)
    end: int
    lit: str  # letters + diacritics (app.arabic.literal), digits ASCII
    key: str  # letters only, exact letter forms, digits ASCII
    fold: str  # folded spelling (app.arabic.folded), digits ASCII


def words(text: str) -> list[Word]:
    out: list[Word] = []
    for m in _WORD.finditer(text or ""):
        lit = arabic.to_ascii_digits(arabic.literal(m.group()))
        for piece in lit.split(" "):  # a ligature such as ﷺ expands to several words
            key = "".join(ch for ch in piece if not arabic.is_diacritic(ch))
            if key:
                out.append(Word(m.start(), m.end(), piece, key, arabic.to_ascii_digits(arabic.folded(piece))))
    return out


# --------------------------------------------------------------------------- distances and alignment


def levenshtein(a, b) -> int:
    """Edit distance between two sequences (Myers/Hyyrö bit-vector; exact, fast enough for whole pages)."""
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    m = len(b)
    peq: dict = {}
    for i, c in enumerate(b):
        peq[c] = peq.get(c, 0) | (1 << i)
    mask, high = (1 << m) - 1, 1 << (m - 1)
    pv, mv, score = mask, 0, m
    for c in a:
        eq = peq.get(c, 0)
        xv = eq | mv
        xh = (((eq & pv) + pv) ^ pv) | eq
        ph = mv | (~(xh | pv) & mask)
        mh = pv & xh
        if ph & high:
            score += 1
        elif mh & high:
            score -= 1
        ph = ((ph << 1) | 1) & mask
        mh = (mh << 1) & mask
        pv = mh | (~(xv | ph) & mask)
        mv = ph & xv
    return score


def align(ref: list, hyp: list) -> list[tuple[str, int | None, int | None]]:
    """Levenshtein alignment with backtrace: [(op, ref index, hyp index)], op in match/sub/del/ins."""
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        ri, row, prev = ref[i - 1], d[i], d[i - 1]
        for j in range(1, m + 1):
            row[j] = min(prev[j - 1] + (ri != hyp[j - 1]), prev[j] + 1, row[j - 1] + 1)
    ops: list[tuple[str, int | None, int | None]] = []
    i, j = n, m
    while i or j:
        if i and j and d[i][j] == d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            ops.append(("match" if ref[i - 1] == hyp[j - 1] else "sub", i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i and d[i][j] == d[i - 1][j] + 1:
            ops.append(("del", i - 1, None))
            i -= 1
        else:
            ops.append(("ins", None, j - 1))
            j -= 1
    ops.reverse()
    return ops


# --------------------------------------------------------------------------- diacritics


def _profile(word: str) -> list[tuple[str, frozenset]]:
    return arabic.diacritic_profile(word)


def diacritic_compare(gt_word: str, ocr_word: str) -> dict:
    """Compare marks on aligned base letters of one aligned word pair."""
    g, o = _profile(gt_word), _profile(ocr_word)
    c = {"letters_compared": 0, "letters_wrong": 0, "marks_missing": 0, "marks_extra": 0}
    for op, gi, oi in align([b for b, _ in g], [b for b, _ in o]):
        if op != "match":
            continue
        gm, om = g[gi][1], o[oi][1]
        if gm or om:
            c["letters_compared"] += 1
            if gm != om:
                c["letters_wrong"] += 1
                c["marks_missing"] += len(gm - om)
                c["marks_extra"] += len(om - gm)
    return c


# --------------------------------------------------------------------------- lexicon (approximate)


def default_quran_cache() -> Path:
    base = os.environ.get("QURAN_CACHE_DIR") or os.path.join(tempfile.gettempdir(), "quran-auditor-cache")
    return Path(base) / "hafs-mushaf-1.json"


def build_lexicon(gt_texts: list[str], quran_cache: Path | None) -> tuple[set[str], dict]:
    """Folded word forms from the cached Quran text (if readable) plus the ground-truth corpus. Approximate."""
    lex: set[str] = set()
    info = {"approximate": True, "quran_cache": None, "quran_forms": 0, "ground_truth_forms": 0,
            "note": "membership in this list approximates 'a valid Arabic word'; it is not a dictionary"}
    if quran_cache is not None:
        try:
            data = json.loads(Path(quran_cache).read_text(encoding="utf-8"))
            q = {w.fold for a in data["ayahs"] for w in words(str(a["text"]))}
            lex |= q
            info["quran_cache"], info["quran_forms"] = str(quran_cache), len(q)
        except (OSError, ValueError, KeyError, TypeError):
            info["quran_cache"] = f"not readable: {quran_cache}"
    g = {w.fold for t in gt_texts for w in words(t)}
    lex |= g
    info["ground_truth_forms"] = len(g)
    info["total_forms"] = len(lex)
    return lex, info


# --------------------------------------------------------------------------- one page


COUNT_KEYS = (
    "gt_words", "ocr_words", "gt_chars_strict", "char_edits_strict", "gt_chars_letters", "char_edits_letters",
    "word_errors_strict", "sub", "del", "ins", "sub_spelling_variant", "plausible_wrong",
    "span_words", "span_sub", "span_del", "span_ins", "span_plausible_wrong", "spans", "spans_word_perfect",
    "diacritic_letters_compared", "diacritic_letters_wrong", "diacritic_marks_missing", "diacritic_marks_extra",
    "span_diacritic_letters_compared", "span_diacritic_letters_wrong", "span_diacritic_marks_missing", "span_diacritic_marks_extra",
)


def _counter() -> dict:
    c: dict = defaultdict(int)
    for k in COUNT_KEYS:
        c[k] = 0
    return c


def score_page(gt_text: str, ocr_text: str, spans: list[dict], lexicon: set[str]) -> dict:
    """All counts for one page. Rates are derived from counts by ``rates``."""
    gw, ow = words(gt_text), words(ocr_text)
    c = _counter()
    c["gt_words"], c["ocr_words"] = len(gw), len(ow)

    gt_strict, ocr_strict = " ".join(w.lit for w in gw), " ".join(w.lit for w in ow)
    gt_letters, ocr_letters = " ".join(w.key for w in gw), " ".join(w.key for w in ow)
    c["gt_chars_strict"], c["char_edits_strict"] = len(gt_strict), levenshtein(gt_strict, ocr_strict)
    c["gt_chars_letters"], c["char_edits_letters"] = len(gt_letters), levenshtein(gt_letters, ocr_letters)

    strict_ops = align([w.lit for w in gw], [w.lit for w in ow])
    c["word_errors_strict"] = sum(op != "match" for op, _, _ in strict_ops)

    # Which ground-truth words fall inside which span.
    span_of: dict[int, int] = {}
    span_rows = []
    for k, s in enumerate(spans):
        idx = [i for i, w in enumerate(gw) if w.start < s["end"] and w.end > s["start"]]
        for i in idx:
            span_of[i] = k
        span_rows.append({"surah": s["surah"], "ayah_start": s["ayah_start"], "ayah_end": s.get("ayah_end", s["ayah_start"]),
                          "start": s["start"], "end": s["end"], "words": len(idx), "sub": 0, "del": 0, "ins": 0,
                          "plausible_wrong": 0, "diacritic_letters_compared": 0, "diacritic_letters_wrong": 0})
    c["span_words"] = len(span_of)

    ops = align([w.key for w in gw], [w.key for w in ow])
    prev_gt = -1
    for op, gi, oi in ops:
        if op == "ins":
            k = span_of.get(prev_gt)
            inside = k is not None and span_of.get(prev_gt + 1) == k
            c["ins"] += 1
            if inside:
                c["span_ins"] += 1
                span_rows[k]["ins"] += 1
            continue
        prev_gt = gi
        k = span_of.get(gi)
        if op == "del":
            c["del"] += 1
            if k is not None:
                c["span_del"] += 1
                span_rows[k]["del"] += 1
            continue
        g, o = gw[gi], ow[oi]
        dc = diacritic_compare(g.lit, o.lit)
        for name in ("letters_compared", "letters_wrong", "marks_missing", "marks_extra"):
            c[f"diacritic_{name}"] += dc[name]
            if k is not None:
                c[f"span_diacritic_{name}"] += dc[name]
        if k is not None:
            span_rows[k]["diacritic_letters_compared"] += dc["letters_compared"]
            span_rows[k]["diacritic_letters_wrong"] += dc["letters_wrong"]
        if op == "match":
            continue
        c["sub"] += 1
        if k is not None:
            c["span_sub"] += 1
            span_rows[k]["sub"] += 1
        if o.fold == g.fold:
            c["sub_spelling_variant"] += 1  # differs only in a folded letter form (hamza seat, ة/ه, ى/ي ...)
        elif o.fold in lexicon:
            c["plausible_wrong"] += 1
            if k is not None:
                c["span_plausible_wrong"] += 1
                span_rows[k]["plausible_wrong"] += 1

    for r in span_rows:
        errs = r["sub"] + r["del"] + r["ins"]
        r["wer"] = _rate(errs, r["words"])
        r["word_perfect"] = errs == 0 and r["words"] > 0
    c["spans"] = len(span_rows)
    c["spans_word_perfect"] = sum(r["word_perfect"] for r in span_rows)
    return {"counts": dict(c), "spans": span_rows}


# --------------------------------------------------------------------------- rates


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 6) if den else None


def rates(c: dict) -> dict:
    g = lambda k: c.get(k, 0)  # noqa: E731
    word_err = g("sub") + g("del") + g("ins")
    span_err = g("span_sub") + g("span_del") + g("span_ins")
    return {
        "cer_strict": _rate(g("char_edits_strict"), g("gt_chars_strict")),
        "cer_letters": _rate(g("char_edits_letters"), g("gt_chars_letters")),
        "wer_strict": _rate(g("word_errors_strict"), g("gt_words")),
        "wer_letters": _rate(word_err, g("gt_words")),
        "wer_in_quran_spans": _rate(span_err, g("span_words")),
        "wer_outside_quran_spans": _rate(word_err - span_err, g("gt_words") - g("span_words")),
        "spans_word_perfect_share": _rate(g("spans_word_perfect"), g("spans")),
        "diacritic_error_rate": _rate(g("diacritic_letters_wrong"), g("diacritic_letters_compared")),
        "diacritic_error_rate_in_spans": _rate(g("span_diacritic_letters_wrong"), g("span_diacritic_letters_compared")),
        "plausible_wrong_per_100_words": _rate(100 * g("plausible_wrong"), g("gt_words")),
        "plausible_wrong_share_of_substitutions": _rate(g("plausible_wrong"), g("sub")),
        "plausible_wrong_in_spans_per_100_span_words": _rate(100 * g("span_plausible_wrong"), g("span_words")),
    }


def _add(total: dict, c: dict) -> None:
    for k, v in c.items():
        total[k] = total.get(k, 0) + v


def time_and_cost(run_pages: list[dict]) -> dict:
    """Summarise only what the run recorded. Missing values stay missing."""
    secs = [float(p["seconds"]) for p in run_pages if isinstance(p.get("seconds"), (int, float))]
    by_cur: dict[str, float] = defaultdict(float)
    priced = 0
    for p in run_pages:
        cost = p.get("cost")
        if isinstance(cost, dict) and isinstance(cost.get("amount"), (int, float)) and cost.get("currency"):
            by_cur[str(cost["currency"])] += float(cost["amount"])
            priced += 1
    return {
        "pages_with_time": len(secs),
        "seconds_total": round(sum(secs), 3) if secs else None,
        "seconds_per_page_mean": round(statistics.mean(secs), 3) if secs else None,
        "seconds_per_page_median": round(statistics.median(secs), 3) if secs else None,
        "seconds_per_page_max": round(max(secs), 3) if secs else None,
        "pages_with_cost": priced,
        "cost_total_by_currency": {k: round(v, 6) for k, v in by_cur.items()} or None,
        "cost_per_page_by_currency": {k: round(v / priced, 6) for k, v in by_cur.items()} if priced else None,
        "note": "read from the run record; pages without a recorded value are not estimated",
    }


# --------------------------------------------------------------------------- manifest


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def load_ground_truth(page: dict, data_dir: Path) -> str:
    if "ground_truth" in page:
        return page["ground_truth"]
    return (data_dir / page["ground_truth_path"]).read_text(encoding="utf-8")


def validate_manifest(manifest: dict, data_dir: Path, manifest_path: Path | None = None, repo_root: Path = ROOT) -> list[str]:
    """Checks the schema cannot express (span bounds, rights vs. location in the repository). Returns errors."""
    errs: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errs.append(f"schema_version must be {SCHEMA_VERSION}")
    pages = manifest.get("pages")
    if not isinstance(pages, list) or not pages:
        return errs + ["pages must be a non-empty list"]
    seen: set[str] = set()
    for n, p in enumerate(pages):
        pid = p.get("page_id")
        where = f"page {pid or n}"
        if not isinstance(pid, str) or not _PAGE_ID.match(pid):
            errs.append(f"{where}: page_id missing or not [A-Za-z0-9_.-]")
        elif pid in seen:
            errs.append(f"{where}: duplicate page_id")
        seen.add(pid)
        if p.get("category") not in CATEGORIES:
            errs.append(f"{where}: category must be one of {sorted(CATEGORIES)}")
        if p.get("script") not in SCRIPTS:
            errs.append(f"{where}: script must be one of {sorted(SCRIPTS)}")
        if p.get("diacritics") not in DIACRITICS_LEVELS:
            errs.append(f"{where}: diacritics must be one of {sorted(DIACRITICS_LEVELS)}")
        r = p.get("rights")
        if not isinstance(r, dict):
            errs.append(f"{where}: rights record missing")
            r = {}
        for f in ("source", "licence", "cleared_by"):
            if not isinstance(r.get(f), str) or not r.get(f).strip():
                errs.append(f"{where}: rights.{f} missing")
        if not isinstance(r.get("cleared_on"), str) or not _DATE.match(r.get("cleared_on", "")):
            errs.append(f"{where}: rights.cleared_on must be YYYY-MM-DD")
        for f in ("may_commit_image", "may_commit_ground_truth"):
            if not isinstance(r.get(f), bool):
                errs.append(f"{where}: rights.{f} must be true or false")
        # Images and ground truth stay out of the repository unless the rights record allows them in.
        if isinstance(p.get("image_path"), str) and r.get("may_commit_image") is not True and _inside(data_dir / p["image_path"], repo_root):
            errs.append(f"{where}: image_path is inside the repository but rights.may_commit_image is not true")
        has_inline, has_path = "ground_truth" in p, "ground_truth_path" in p
        if has_inline == has_path:
            errs.append(f"{where}: give exactly one of ground_truth / ground_truth_path")
            continue
        if r.get("may_commit_ground_truth") is not True:
            if has_path and _inside(data_dir / p["ground_truth_path"], repo_root):
                errs.append(f"{where}: ground_truth_path is inside the repository but rights.may_commit_ground_truth is not true")
            if has_inline and manifest_path is not None and _inside(manifest_path, repo_root):
                errs.append(f"{where}: inline ground truth in a manifest inside the repository needs rights.may_commit_ground_truth")
        checkers = p.get("ground_truth_checked_by")
        if not isinstance(checkers, list) or len({str(x).strip() for x in checkers if str(x).strip()}) < 2:
            errs.append(f"{where}: ground_truth_checked_by needs two different people")
        try:
            gt = load_ground_truth(p, data_dir)
        except OSError as e:
            errs.append(f"{where}: ground truth not readable ({e.__class__.__name__})")
            continue
        last_end = -1
        for s in sorted(p.get("quran_spans") or [], key=lambda s: s.get("start", 0)):
            st, en, su = s.get("start"), s.get("end"), s.get("surah")
            a1, a2 = s.get("ayah_start"), s.get("ayah_end", s.get("ayah_start"))
            if not (isinstance(st, int) and isinstance(en, int) and 0 <= st < en <= len(gt)):
                errs.append(f"{where}: span {st}-{en} outside the ground truth (length {len(gt)})")
                continue
            if st < last_end:
                errs.append(f"{where}: span {st}-{en} overlaps the previous span")
            last_end = en
            if not (isinstance(su, int) and su in AYAH_COUNTS):
                errs.append(f"{where}: span {st}-{en} has no valid surah")
            elif not (isinstance(a1, int) and isinstance(a2, int) and 1 <= a1 <= a2 <= AYAH_COUNTS[su]):
                errs.append(f"{where}: span {st}-{en} ayah range {a1}-{a2} is not in surah {su}")
            if not any(w.start < en and w.end > st for w in words(gt)):
                errs.append(f"{where}: span {st}-{en} contains no word")
    return errs


def span_boundary_warnings(manifest: dict, data_dir: Path) -> list[str]:
    out = []
    for p in manifest["pages"]:
        gt = load_ground_truth(p, data_dir)
        for s in p.get("quran_spans") or []:
            for w in words(gt):
                if (w.start < s["start"] < w.end) or (w.start < s["end"] < w.end):
                    out.append(f"page {p['page_id']}: span {s['start']}-{s['end']} cuts the word at {w.start}-{w.end}; the whole word is counted")
    return out


# --------------------------------------------------------------------------- whole run


def score(manifest: dict, run: dict, data_dir: Path, quran_cache: Path | None) -> dict:
    gt_by_page = {p["page_id"]: load_ground_truth(p, data_dir) for p in manifest["pages"]}
    lexicon, lex_info = build_lexicon(list(gt_by_page.values()), quran_cache)
    run_pages = {p["page_id"]: p for p in run.get("pages", []) if isinstance(p, dict) and "page_id" in p}
    total: dict = {}
    groups: dict[str, dict[str, dict]] = {"category": {}, "script": {}, "diacritics": {}}
    page_rows, failed = [], []
    for p in manifest["pages"]:
        pid = p["page_id"]
        rp = run_pages.get(pid)
        text = None
        if rp is not None and not rp.get("error"):
            if isinstance(rp.get("text"), str):
                text = rp["text"]
            elif isinstance(rp.get("text_path"), str):
                text = (data_dir / rp["text_path"]).read_text(encoding="utf-8")
        if text is None:  # a page the engine did not return counts as all words deleted, never skipped
            failed.append({"page_id": pid, "reason": "missing from run" if rp is None else (rp.get("error") or "no text")})
            text = ""
        res = score_page(gt_by_page[pid], text, p.get("quran_spans") or [], lexicon)
        _add(total, res["counts"])
        for g in groups:
            _add(groups[g].setdefault(p[g], {}), res["counts"])
        page_rows.append({"page_id": pid, "category": p["category"], "script": p["script"], "diacritics": p["diacritics"],
                          "seconds": (rp or {}).get("seconds"), "cost": (rp or {}).get("cost"),
                          "rates": rates(res["counts"]), "counts": res["counts"], "spans": res["spans"]})
    return {
        "engine": run.get("engine"),
        "run_started_at": run.get("started_at"),
        "set_id": manifest.get("set_id"),
        "pages": len(manifest["pages"]),
        "pages_failed": failed,
        "overall": {"rates": rates(total), "counts": total},
        "by_group": {g: {k: {"pages": sum(1 for p in manifest["pages"] if p[g] == k), "rates": rates(v)} for k, v in vals.items()}
                     for g, vals in groups.items()},
        "time_and_cost": time_and_cost([run_pages[p["page_id"]] for p in manifest["pages"] if p["page_id"] in run_pages]),
        "lexicon": lex_info,
        "per_page": page_rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--run", required=True, type=Path, help="engine run record (JSON)")
    ap.add_argument("--data-dir", type=Path, help="base for ground_truth_path / text_path (default: the manifest's folder)")
    ap.add_argument("--quran-cache", type=Path, default=None, help="cached Quranpedia text for the word list (default: the app's cache path)")
    ap.add_argument("--no-quran-lexicon", action="store_true", help="build the word list from the ground truth only")
    ap.add_argument("--out", type=Path, help="write the full report here (JSON); a summary is printed either way")
    a = ap.parse_args(argv)
    manifest = json.loads(a.manifest.read_text(encoding="utf-8"))
    run = json.loads(a.run.read_text(encoding="utf-8"))
    data_dir = a.data_dir or a.manifest.parent
    errs = validate_manifest(manifest, data_dir, a.manifest)
    if errs:
        print("manifest is not valid; nothing scored:", *errs, sep="\n  ", file=sys.stderr)
        return 2
    for w in span_boundary_warnings(manifest, data_dir):
        print("warning:", w, file=sys.stderr)
    cache = None if a.no_quran_lexicon else (a.quran_cache or default_quran_cache())
    report = score(manifest, run, data_dir, cache)
    if a.out:
        a.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("engine", "set_id", "pages", "pages_failed")}, ensure_ascii=False))
    print(json.dumps(report["overall"]["rates"], indent=1))
    print(json.dumps(report["time_and_cost"], ensure_ascii=False, indent=1))
    print(f"word list: {report['lexicon']['total_forms']} forms (approximate; quran cache: {report['lexicon']['quran_cache']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
