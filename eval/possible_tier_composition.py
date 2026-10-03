"""What the «possible» tier holds on the two labelled article sets (a short and a long one): how many of its items overlap a gold quotation, by reason code.

    python eval/possible_tier_composition.py [--out eval/results]

Written 4 Oct 2026 to decide how the interface should order «possible» items (docs/EVALUATION.md); it changes no rule and tunes nothing.
Source-based path only (no model). A finding "overlaps gold" when its span overlaps any occurrence of a gold quotation's text in the article;
the labels are the sets' own (author-written, not reviewed by a specialist), so these are counts on development data, not a precision estimate.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import app.audit as audit  # noqa: E402

SETS = ["eval/articles_frozen.json", "eval/articles_long_20261003.json"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    audit.get_provider = lambda: None  # no model, whatever the environment says
    counts: dict[str, Counter] = defaultdict(Counter)
    items = []
    for path in SETS:
        for case in json.loads((ROOT / path).read_text(encoding="utf-8"))["cases"]:
            text = case["article"]
            spans = []
            for g in case["gold"]:
                i = text.find(g["quote"])
                while i >= 0:
                    spans.append((i, i + len(g["quote"])))
                    i = text.find(g["quote"], i + 1)
            for f in audit.run_audit(text)["findings"]:
                det = f.get("detection") or {}
                if det.get("tier") != "possible":
                    continue
                key = ",".join(det.get("codes") or [])
                gold = any(a < f["end"] and f["start"] < b for a, b in spans)
                counts[key]["gold" if gold else "not_gold"] += 1
                items.append({"set": Path(path).name, "case": case["id"], "quote": f["quote"], "codes": key, "overlaps_gold": gold})
    result = {"written": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "sets": SETS, "by_codes": {k: dict(v) for k, v in sorted(counts.items())}, "items": items}
    for k, v in result["by_codes"].items():
        print(f"{k:28s} overlaps gold {v.get('gold', 0):3d}   does not {v.get('not_gold', 0):3d}")
    if args.out:
        out = Path(args.out) / f"possible-tier-{time.strftime('%Y%m%d-%H%M%S')}.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print("wrote", out)


if __name__ == "__main__":
    main()
