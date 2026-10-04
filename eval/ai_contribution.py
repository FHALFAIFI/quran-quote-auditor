"""What the model's proposals change in the audit: the same articles, the same code, with and without the recorded answer.

    python eval/ai_contribution.py --evidence <dir written by eval/ai_record.py> --cases eval/cases.json [--cases ...] \
        [--tag <tag>] [--out eval/results]

No model is called. For every article whose recorded call answered (outcome ok), the audit runs twice in-process:
A without a model, B with a stand-in provider that returns exactly the recorded proposals (the production code path in
``app.audit.run_audit``, including locating, merging, grading and ``ai_role``). Articles whose call failed are counted
as failures (the product then shows A, by design) and are not part of the paired comparison.

Per finding of B: ``ai_role`` only / also / overlap / none. A finding only the model proposed is classified against the
labels as a TRUE ADDITIONAL quotation (it covers at least half of a gold span that A did not find), a duplicate of a gold
quotation A already found, a hit on a labelled negative or formula, or a false possible item on unlabelled text.
Harm checks: every finding of A must reappear in B with the same span, tier, verdicts and changes (the model may only add);
any difference is listed.

The aggregate output holds counts and the short quoted spans the model proposed in labelled (published) evaluation sets;
the raw records stay in the private evidence directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.audit as audit  # noqa: E402
from app.extraction.base import ExtractionProvider, RawSuggestion  # noqa: E402
from app.extraction.status import CallTracker  # noqa: E402

COMPARE = ("start", "end", "quote", "wording", "reference", "source", "correction", "changes", "start_boundary", "end_boundary")


class Replay(ExtractionProvider):
    name, label = "groq", "replay of a recorded answer"

    def __init__(self, proposals: list[dict], model: str):
        self.proposals, self.model, self.used_model = proposals, model, model
        self.tracker = CallTracker()

    def available(self) -> bool:
        return True

    def extract(self, article: str) -> list[RawSuggestion]:
        self.tracker.record("ok", self.model, None, 200, 0)
        return [RawSuggestion(p["quote"], p.get("reference_text") or None) for p in self.proposals]


def _ov(a0, a1, b0, b1) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def _strip(f: dict) -> dict:
    out = {k: f.get(k) for k in COMPARE}
    det = dict(f["detection"])
    for k in ("ai_role", "ai_spans"):
        det.pop(k, None)
    out["detection"] = det
    return out


def load_records(evidence: Path) -> dict[str, dict]:
    recs: dict[str, dict] = {}
    for f in sorted(evidence.glob("record-*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["id"] not in recs or r["outcome"] == "ok":
                recs[r["id"]] = r  # the answered call wins over an earlier failure of the same article
    return recs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--cases", action="append", required=True)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    recs = load_records(Path(args.evidence))
    totals = Counter()
    per_set, details, harms, calls = {}, [], [], []
    for p in args.cases:
        path = Path(p)
        if path.is_dir():
            cases = [{"id": f.stem, "article": f.read_text(encoding="utf-8").replace("\r\n", "\n").strip(), "gold": [], "negatives": []}
                     for f in sorted(path.glob("*.txt"))]
            prefix = "samples"
        else:
            cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
            prefix = path.stem
        c = Counter()
        for case in cases:
            aid = f"{prefix}/{case['id']}"
            r = recs.get(aid)
            if r is None:
                c["not_recorded"] += 1
                continue
            calls.append({k: r.get(k) for k in ("id", "outcome", "elapsed_ms", "at")} | {"http_status": (r.get("http") or {}).get("status"),
                         "tokens": ((r.get("http") or {}).get("usage") or {}).get("total_tokens"), "error_body_type": (r.get("error_body") or {}).get("type")})
            c["calls"] += 1
            if r["outcome"] != "ok":
                c["call_failed"] += 1
                c[f"failed_http_{(r.get('http') or {}).get('status')}"] += 1
                continue
            art = case["article"]
            audit.get_provider = lambda: None
            a = audit.run_audit(art)
            rp = Replay(r["proposals"], (r.get("http") or {}).get("model") or r.get("model_configured"))
            audit.get_provider = lambda rp=rp: rp
            b = audit.run_audit(art)
            ai = b["ai"]
            c["answered"] += 1
            c["proposed"] += ai["proposed"]
            c["located"] += ai["located"]
            c["discarded"] += ai["discarded"]
            c["also_found"] += ai["also_found"]
            c["overlapped"] += ai["overlapped"]
            c["empty_answers"] += ai["proposed"] == 0
            gold = case.get("gold", [])
            negs = list(case.get("negatives", [])) + list(case.get("formulas", []))

            def gold_hit(f):
                for g in gold:
                    g0 = g.get("start", art.find(g["quote"]))
                    g1 = g.get("end", g0 + len(g["quote"]))
                    if g0 >= 0 and _ov(f["start"], f["end"], g0, g1) >= 0.5 * (g1 - g0):
                        return g
                return None

            a_found_gold = {id(g) for f in a["findings"] if (g := gold_hit(f)) is not None}
            for f in b["findings"]:
                role = f["detection"]["ai_role"]
                if role != "only":
                    continue
                c["added_only"] += 1
                g = gold_hit(f)
                if g is not None and id(g) not in a_found_gold:
                    kind = "true_additional_quotation"
                elif g is not None:
                    kind = "duplicate_of_found_gold"
                elif any(_ov(f["start"], f["end"], art.find(n), art.find(n) + len(n)) > 0 for n in negs if art.find(n) >= 0):
                    kind = "on_labelled_negative_or_formula"
                elif not gold and prefix == "samples":
                    kind = "unlabelled_sample_text"
                else:
                    kind = "false_possible_on_unlabelled_text"
                c[kind] += 1
                details.append({"article": aid, "quote": f["quote"], "kind": kind, "tier": f["detection"]["tier"],
                                "codes": f["detection"].get("codes"), "basis": f["detection"].get("basis"),
                                "wording": f["wording"]["status"],
                                "changes": [(ch["kind"], ch.get("replacement")) for ch in f["changes"] if not ch["optional"]]})
            # harm: every finding without the model must be unchanged with it
            bspans = {(f["start"], f["end"]): f for f in b["findings"]}
            for f in a["findings"]:
                g = bspans.get((f["start"], f["end"]))
                if g is None:
                    harms.append({"article": aid, "quote": f["quote"], "problem": "missing with the model"})
                elif _strip(f) != _strip(g):
                    diff = [k for k in _strip(f) if _strip(f)[k] != _strip(g)[k]]
                    harms.append({"article": aid, "quote": f["quote"], "problem": f"changed: {diff}"})
            c["chars"] += len(art)
        per_set[prefix] = dict(c)
        totals.update(c)
    totals["harms"] = len(harms)
    out = {"tag": args.tag, "evidence_dir_name": Path(args.evidence).name, "totals": dict(totals), "per_set": per_set,
           "model_only_findings": details, "harms": harms, "calls": calls}
    path = ROOT / "eval" / "results" / f"ai-contribution-{datetime.now().strftime('%Y%m%d-%H%M%S')}{'-' + args.tag if args.tag else ''}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"totals": dict(totals), "per_set": per_set}, ensure_ascii=False, indent=1))
    for d in details:
        print(f"ONLY  {d['article']:34s} {d['kind']:34s} tier={d['tier']} «{d['quote']}» changes={d['changes']}")
    for h in harms:
        print(f"HARM  {h}")
    print(f"saved {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
