"""Score the audit on the hard-quotation diagnostic sets (eval/hard_quotes_*_20261004.json). No model is called.

    python eval/run_hard_quotes.py --cases eval/hard_quotes_dev_20261004.json --tag <tag>

The four measures are reported separately and never folded into one accuracy figure:

1. recall          a finding covers at least half of the gold span AND the gold verse is offered (as the proposed verse,
                   an alternative or a choice); split by expected detection (required / desirable), error type and context.
2. false possibilities  findings on the labelled negatives and on unlabelled text, by tier, per 10,000 characters.
3. wrong "matched"  a misquotation whose finding reads wording "matched" (any tier).
4. correction safety
     before the writer acts: a replacement proposed for a correct quotation, a wrong replacement, a replacement where the
       label forbids one before confirmation, a replacement word or reference that is not from the finding's own verse,
       any change proposed on a negative;
     after a simulated confirmation: the writer selects the gold span and picks the gold verse from the choices shown
       (only when the audit offered it) through the same endpoint the page uses (``run_phrase``); the replacement is
       checked against the gold wording. The number of writer actions is counted (1 = pick the verse; 2 = adjust the
       boundary, then pick).

The simulation assumes a writer who knows which verse they meant; it measures what the product offers once they say so,
not whether a writer would find it.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.audit as audit  # noqa: E402
from app import arabic  # noqa: E402
from app.references import parse_reference  # noqa: E402

sys.path.insert(0, str(ROOT / "eval"))
from run_eval import grade_corrections  # noqa: E402


def _ov(a0, a1, b0, b1) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def _letters_words(text: str) -> list[str]:
    return [arabic.letters(t.raw) for t in arabic.tokenize(text)]


def _offered(f: dict) -> list[tuple[int, int, int]]:
    blocks = ([f["source"]] if f.get("source") else []) + [a["source"] for a in f.get("alternatives", []) if a.get("source")]
    out = [(b["surah"], b["ayah_start"], b["ayah_end"]) for b in blocks]
    out += [(c["surah"], c["ayah_start"], c["ayah_end"]) for c in f.get("choices", [])]
    return out


def _covers(loc, g) -> bool:
    s, a0, a1 = loc
    return s == g["surah"] and a0 <= g["ayah_end"] and g["ayah_start"] <= a1


def _changes_from_source(f: dict) -> list[str]:
    """Problems with proposed (non-optional) changes: words or references that are not from the finding's own verse."""
    problems = []
    src = f.get("source")
    src_words = set(_letters_words(src["matched_text"])) if src and src.get("matched_text") else set()
    if src and src.get("segments"):
        for seg in src["segments"]:
            src_words |= {arabic.letters(w) for w in seg.get("words", [])}
    for c in f.get("changes", []):
        if c.get("optional"):
            continue
        if c["kind"] in ("wording", "diacritics"):
            for w in _letters_words(c.get("replacement") or ""):
                if w not in src_words:
                    problems.append(f"word «{w}» not in {src and src['label']}")
        elif c["kind"] == "reference":
            r = parse_reference(c.get("replacement") or "")
            if not src or r is None or (r.surah, r.ayah_start, r.ayah_end or r.ayah_start) != (src["surah"], src["ayah_start"], src["ayah_end"]):
                problems.append(f"reference «{c.get('replacement')}» is not the verse shown ({src and src['label']})")
    return problems


def _simulate_confirm(art: str, g: dict, f: dict) -> dict:
    """The writer selects the gold span and picks the gold verse (only if the audit offered it)."""
    if not any(_covers(loc, g) for loc in _offered(f)):
        return {"possible": False, "why": "gold verse not offered"}
    same_span = (f["start"], f["end"]) == (g["start"], g["end"])
    res = audit.run_phrase(art, g["start"], g["end"], g["surah"], g["ayah_start"], g["ayah_end"], finding_id=f["id"])
    h = res["finding"]
    corr = grade_corrections(h, g)
    return {"possible": True, "actions": 1 if same_span else 2, "wording": h["wording"]["status"],
            "fix": corr["wording_fix"], "false_fix": corr["false_fix"], "source_problems": _changes_from_source(h)}


def score(path: Path, tag: str) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows, neg_rows, extra, chars = [], [], [], 0
    for case in data["cases"]:
        art = case["article"]
        chars += len(art)
        res = audit.run_audit(art)
        used = set()
        for g in case["gold"]:
            g0, g1 = g.get("start", art.find(g["quote"])), g.get("end")
            g1 = g1 if g1 is not None else g0 + len(g["quote"])
            g = {**g, "start": g0, "end": g1}
            hit = next((f for f in res["findings"] if _ov(f["start"], f["end"], g0, g1) >= 0.5 * (g1 - g0)), None)
            exp = g.get("expect") or {}
            row = {"case": case["id"], "quote": g["quote"], "error": g.get("error"), "context": g.get("context", []),
                   "detect": exp.get("detect", "required"), "wording_label": g["wording"], "found": hit is not None}
            if hit:
                used.add(hit["id"])
                det = hit["detection"]
                offered = any(_covers(loc, g) for loc in _offered(hit))
                corr = grade_corrections(hit, g)
                fixes = [c for c in hit["changes"] if not c["optional"] and c["kind"] in ("wording", "diacritics")]
                row.update({
                    "span": [hit["start"], hit["end"]], "span_exact": (hit["start"], hit["end"]) == (g0, g1),
                    "tier": det["tier"], "kind": det["kind"], "codes": det.get("codes"), "unconfirmed": det["unconfirmed"],
                    "verse_offered": offered, "detected": offered,
                    "wording": hit["wording"]["status"], "reference": hit["reference"]["status"],
                    "wrong_matched": g["wording"] != "correct" and hit["wording"]["status"] == "matched",
                    "fix": corr["wording_fix"], "false_fix": corr["false_fix"], "false_reference_fix": corr["false_reference_fix"],
                    "reference_fix": corr["reference_fix"],
                    "forbidden_fix": bool(fixes) and exp.get("auto_replacement") == "forbidden",
                    "source_problems": _changes_from_source(hit),
                    "start_boundary": (hit.get("start_boundary") or {}).get("status"),
                    "end_boundary": (hit.get("end_boundary") or {}).get("status"),
                })
                if det["unconfirmed"] or hit["wording"]["status"] != "matched" or not row["span_exact"]:
                    row["confirm"] = _simulate_confirm(art, g, hit)
            else:
                row["detected"] = False
            rows.append(row)
        negs = case.get("negatives_detail") or [{"text": n, "kind": "negative"} for n in case.get("negatives", [])]
        for f in res["findings"]:
            if f["id"] in used:
                continue
            det = f["detection"]
            entry = {"case": case["id"], "quote": f["quote"], "tier": det["tier"], "codes": det.get("codes"),
                     "confirmed": not det["unconfirmed"], "wording": f["wording"]["status"],
                     "changes": [(c["kind"], c.get("replacement")) for c in f["changes"] if not c["optional"]]}
            neg = None
            for n in negs:
                n0 = n.get("start", art.find(n["text"]))
                n1 = n.get("end", n0 + len(n["text"]))
                if _ov(f["start"], f["end"], n0, n1) > 0:
                    neg = n
                    break
            if neg is not None:
                neg_rows.append({**entry, "negative": neg["text"], "neg_kind": neg.get("kind")})
            else:
                extra.append(entry)

    def frac(sub):
        return f"{sum(r['detected'] for r in sub)}/{len(sub)}"

    by = defaultdict(list)
    for r in rows:
        by[("detect", r["detect"])].append(r)
        by[("error", r["error"])].append(r)
        for c in r["context"] or ["none"]:
            by[("context", c)].append(r)
    det = [r for r in rows if r.get("found")]
    mis = [r for r in det if r["wording_label"] != "correct"]
    conf = [r for r in det if r.get("confirm", {}).get("possible")]
    summary = {
        "cases_file": str(path.relative_to(ROOT)), "tag": tag, "articles": len(data["cases"]), "characters": chars,
        "gold": len(rows),
        "1_recall": {
            "detected_with_gold_verse_offered": frac(rows),
            "required": frac(by[("detect", "required")]), "desirable": frac(by[("detect", "desirable")]),
            "found_but_gold_verse_not_offered": sum(1 for r in det if not r["verse_offered"]),
            "by_error": {k[1]: frac(v) for k, v in sorted(by.items(), key=lambda kv: str(kv[0])) if k[0] == "error"},
            "by_context": {k[1]: frac(v) for k, v in sorted(by.items(), key=lambda kv: str(kv[0])) if k[0] == "context"},
            "tiers_of_detected": dict(Counter(r["tier"] for r in det)),
            "span_exact": sum(r["span_exact"] for r in det),
        },
        "2_false_possibilities": {
            "on_negatives": len(neg_rows), "on_negatives_presented_confirmed": sum(n["confirmed"] for n in neg_rows),
            "on_negatives_by_kind": dict(Counter(n["neg_kind"] for n in neg_rows)),
            "on_unlabelled_text": len(extra), "on_unlabelled_presented_confirmed": sum(e["confirmed"] for e in extra),
            "per_10k_chars": round(10000 * (len(neg_rows) + len(extra)) / max(1, chars), 2),
        },
        "3_wrong_matched": {"misquotations_detected": len(mis), "reported_matched": sum(r["wrong_matched"] for r in mis),
                            "wording_of_misquotations": dict(Counter(r["wording"] for r in mis)),
                            "wording_of_correct_quotes": dict(Counter(r["wording"] for r in det if r["wording_label"] == "correct"))},
        "4_correction_safety": {
            "before_confirmation": {
                "fix_on_correct_quote": sum(r["false_fix"] for r in det),
                "reference_fix_on_correct_reference": sum(r["false_reference_fix"] for r in det),
                "wrong_fix": sum(r["fix"] == "wrong" for r in det),
                "right_fix": sum(r["fix"] == "ok" for r in det),
                "fix_where_label_forbids": sum(r["forbidden_fix"] for r in det),
                "words_or_refs_not_from_chosen_verse": sum(bool(r["source_problems"]) for r in det),
                "changes_on_negatives_or_unlabelled": sum(bool(e["changes"]) for e in neg_rows + extra),
            },
            "after_simulated_confirmation": {
                "simulated": len(conf),
                "misquotes_right_fix": sum(r["confirm"]["fix"] == "ok" for r in conf if r["wording_label"] != "correct"),
                "misquotes_wrong_fix": sum(r["confirm"]["fix"] == "wrong" for r in conf if r["wording_label"] != "correct"),
                "misquotes_no_fix": sum(r["confirm"]["fix"] is None for r in conf if r["wording_label"] != "correct"),
                "correct_quotes_given_a_fix": sum(bool(r["confirm"]["false_fix"]) for r in conf),
                "words_not_from_chosen_verse": sum(bool(r["confirm"]["source_problems"]) for r in conf),
                "actions": dict(Counter(r["confirm"]["actions"] for r in conf)),
                "not_settleable_gold_verse_not_offered": sum(1 for r in det if r.get("confirm") and not r["confirm"]["possible"]),
            },
        },
    }
    out = ROOT / "eval" / "results" / f"hard-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{path.stem}{'-' + tag if tag else ''}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows, "negative_hits": neg_rows, "extra_findings": extra},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    return {"summary": summary, "rows": rows, "neg": neg_rows, "extra": extra, "out": out}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--tag", default="")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    audit.get_provider = lambda: None  # deterministic: no model
    r = score(Path(args.cases).resolve(), args.tag)
    print(json.dumps(r["summary"], ensure_ascii=False, indent=1))
    if not args.quiet:
        for row in r["rows"]:
            if not row["detected"]:
                print(f"MISSED  {row['case']} [{row['error']}/{','.join(row['context'])}] «{row['quote']}»"
                      + (f" (found, verse not offered; tier {row.get('tier')})" if row.get("found") else ""))
            elif row["wrong_matched"] or row["false_fix"] or row["fix"] == "wrong" or row["source_problems"] or row["forbidden_fix"]:
                print(f"SAFETY  {row['case']} «{row['quote']}» {row}")
        for n in r["neg"]:
            print(f"NEG     {n['case']} «{n['quote']}» tier={n['tier']} codes={n['codes']} confirmed={n['confirmed']} ({n['neg_kind']})")
        for e in r["extra"]:
            print(f"EXTRA   {e['case']} «{e['quote']}» tier={e['tier']} codes={e['codes']} confirmed={e['confirmed']}")
    print(f"saved {r['out'].relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
