"""Score the pipeline on the hand-labelled set (eval/cases.json).

    python eval/run_eval.py --mode fallback      # no AI (reduced mode), deterministic
    python eval/run_eval.py --mode ai            # uses GEMINI_API_KEY; only valid if every case ran with mode == "ai"

Writes eval/results/<mode>-<timestamp>.json and prints a summary. "Uncertain"
answers are counted as abstentions, separately from wrong verdicts. The most
important safety numbers are false "matched" wording and false "matched"
references, which should be zero.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.audit as audit  # noqa: E402

REF_EXPECT = {"correct": "matched", "incorrect": "incorrect", "out_of_range": "incorrect", "missing": "missing", "partial": "uncertain"}


def expected_reference(g: dict) -> str:
    if g["reference"] == "surah_only":  # surah named without ayah: confirms only an unambiguous quote
        return "uncertain" if g["ambiguous"] else "matched"
    return REF_EXPECT[g["reference"]]


def expected_wording(g: dict) -> str:
    if g["wording"] != "correct":
        return "difference"
    words = len(g["correct_text"].split())
    if (g["ambiguous"] or words < 3) and g["reference"] != "correct":
        return "uncertain"
    return "matched"


def overlap(a0, a1, b0, b1) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def grade(actual: str, expected: str) -> str:
    if actual == expected:
        return "correct"
    if actual == "uncertain":
        return "abstained"
    return "wrong"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["fallback", "ai"], required=True)
    args = ap.parse_args()
    if args.mode == "fallback":
        audit.get_provider = lambda: None

    data = json.loads((ROOT / "eval" / "cases.json").read_text(encoding="utf-8"))
    rows, neg_hits, extra_findings, modes, timings = [], [], [], Counter(), []
    for case in data["cases"]:
        art = case["article"]
        t = time.monotonic()
        res = audit.run_audit(art)
        timings.append(time.monotonic() - t)
        modes[res["mode"]] += 1
        used = set()
        for g in case["gold"]:
            g0 = art.index(g["quote"])
            g1 = g0 + len(g["quote"])
            hit = None
            for f in res["findings"]:
                if overlap(f["start"], f["end"], g0, g1) >= 0.5 * (g1 - g0):
                    hit = f
                    used.add(f["id"])
                    break
            row = {"case": case["id"], "quote": g["quote"], "tags": g["tags"], "detected": hit is not None}
            if hit:
                w_exp, r_exp = expected_wording(g), expected_reference(g)
                w_act, r_act = hit["wording"]["status"], hit["reference"]["status"]
                src = hit["source"]
                loc_ok = None
                if src and not (g["ambiguous"] and g["reference"] != "correct"):
                    loc_ok = (src["surah"], src["ayah_start"], src["ayah_end"]) == (g["surah"], g["ayah_start"], g["ayah_end"])
                row.update({
                    "detected_by": hit["detected_by"],
                    "wording_expected": w_exp, "wording_actual": w_act, "wording_level": hit["wording"]["level"],
                    "wording_grade": grade(w_act, w_exp),
                    "false_verified_wording": w_act == "matched" and g["wording"] != "correct",
                    "reference_expected": r_exp, "reference_actual": r_act, "reference_grade": grade(r_act, r_exp),
                    "false_verified_reference": r_act == "matched" and g["reference"] not in ("correct", "surah_only"),
                    "location_ok": loc_ok, "needs_review": hit["needs_review"],
                })
            rows.append(row)
        for f in res["findings"]:
            if f["id"] in used:
                continue
            neg = next((n for n in case["negatives"] if overlap(f["start"], f["end"], art.index(n), art.index(n) + len(n)) > 0), None)
            (neg_hits if neg else extra_findings).append({"case": case["id"], "quote": f["quote"], "negative": neg})

    if args.mode == "ai" and set(modes) != {"ai"}:
        print(f"NOT AN AI RESULT: modes observed {dict(modes)} — at least one case fell back. Nothing recorded as AI.")
        return 2

    det = [r for r in rows if r["detected"]]
    summary = {
        "mode": args.mode,
        "modes_observed": dict(modes),
        "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cases": len(data["cases"]),
        "gold_quotations": len(rows),
        "detected": len(det),
        "detection_by_tag": {},
        "wording": dict(Counter(r["wording_grade"] for r in det)),
        "reference": dict(Counter(r["reference_grade"] for r in det)),
        "location_ok": dict(Counter(str(r["location_ok"]) for r in det)),
        "false_verified_wording": sum(r["false_verified_wording"] for r in det),
        "false_verified_reference": sum(r["false_verified_reference"] for r in det),
        "negative_hits": len(neg_hits),
        "other_extra_findings": len(extra_findings),
        "seconds_per_article_max": round(max(timings), 2),
        "seconds_per_article_mean": round(sum(timings) / len(timings), 2),
    }
    by_tag = defaultdict(lambda: [0, 0])
    for r in rows:
        for t in r["tags"]:
            by_tag[t][1] += 1
            by_tag[t][0] += r["detected"]
    summary["detection_by_tag"] = {t: f"{d}/{n}" for t, (d, n) in sorted(by_tag.items())}

    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{args.mode}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows, "negative_hits": neg_hits, "extra_findings": extra_findings}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for r in rows:
        if not r["detected"]:
            print(f"MISSED   {r['case']}: «{r['quote']}» tags={r['tags']}")
        elif r["wording_grade"] != "correct" or r["reference_grade"] != "correct" or r["location_ok"] is False:
            print(f"MISMATCH {r['case']}: «{r['quote']}» wording {r['wording_actual']} (exp {r['wording_expected']}), "
                  f"ref {r['reference_actual']} (exp {r['reference_expected']}), location_ok={r['location_ok']}")
    for n in neg_hits:
        print(f"NEG-HIT  {n['case']}: «{n['quote']}»")
    for e in extra_findings:
        print(f"EXTRA    {e['case']}: «{e['quote']}»")
    print(f"saved {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
