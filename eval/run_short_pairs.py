"""Score unmarked two-word quotations (docs/SHORT_PHRASE_PROTOCOL_20261005.md). The full audit runs with the model off.

    python eval/run_short_pairs.py --tag <tag> SET [SET ...]

SET is one of
  * a split written for this protocol (``eval/short_phrases_{dev,heldout}_20261005.json``: cases with labelled ``spans``),
  * an older labelled set in ``eval/`` (cases with ``gold``; an unmarked gold quotation counts as ``quote``, any other as ``marked``),
  * ``wiki:<path>[:even|:odd]``, a local sample of Wikipedia lead sections (not committed; every pair surfaced there counts as false).

Measures (each reported apart, never folded into one figure):
  recall   two-word spans labelled ``quote`` overlapped by any finding (and by a «pair» finding);
  false    «pair» findings that overlap no span labelled quote / marked / allusion, per 10,000 characters (over an allusion: counted apart).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ["AI_PROVIDER"] = "none"
for _k in [k for k in os.environ if k.startswith(("GROQ_", "GEMINI_"))]:
    del os.environ[_k]

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.audit as audit  # noqa: E402


def _zones(article: str, spans: list[dict]) -> list[tuple[int, int, str, int]]:
    out = []
    for sp in spans:
        pos = -1
        for _ in range(int(sp.get("occurrence", 1))):
            pos = article.find(sp["text"], pos + 1)
            if pos < 0:
                raise SystemExit(f"span not found: {sp['text']!r}")
        out.append((pos, pos + len(sp["text"]), sp["label"], len(sp["text"].split())))
    return out


def load(spec: str) -> tuple[str, list[tuple[str, str, list]]]:
    if spec.startswith("wiki:"):
        parts = spec.split(":")
        half = parts[2] if len(parts) > 2 else None
        pages = json.loads(Path(parts[1]).read_text(encoding="utf-8"))["pages"]
        keep = [p for p in pages if half is None or p["pageid"] % 2 == (0 if half == "even" else 1)]
        return f"wiki-{half or 'all'}", [(str(p["pageid"]), p["text"], []) for p in keep]
    d = json.loads(Path(spec).read_text(encoding="utf-8"))
    rows = []
    for c in d["cases"]:
        if "spans" in c:
            rows.append((c["id"], c["article"], _zones(c["article"], c["spans"])))
            continue
        zones = []
        for g in c.get("gold", []):
            q, pos = g["quote"], c["article"].find(g["quote"])
            while pos >= 0:
                zones.append((pos, pos + len(q), "quote" if g.get("unmarked") else "marked", len(q.split())))
                pos = c["article"].find(q, pos + 1)
        rows.append((c["id"], c["article"], zones))
    return Path(spec).stem, rows


def score(name: str, rows: list) -> dict:
    chars = 0
    gold2, found_any, found_pair = [], [], []
    pairs_true, pairs_allusion, pairs_false = [], [], []
    for cid, art, zones in rows:
        chars += len(art)
        findings = audit.run_audit(art)["findings"]
        for z in zones:
            if z[2] == "quote" and z[3] == 2:
                gold2.append((cid, art[z[0]:z[1]]))
                over = [f for f in findings if f["start"] < z[1] and z[0] < f["end"]]
                if over:
                    found_any.append((cid, art[z[0]:z[1]]))
                if any("pair" in (f["detection"].get("codes") or []) for f in over):
                    found_pair.append((cid, art[z[0]:z[1]]))
        for f in findings:
            if "pair" not in (f["detection"].get("codes") or []):
                continue
            hit = [z for z in zones if z[0] < f["end"] and f["start"] < z[1]]
            row = {"case": cid, "text": art[f["start"]:f["end"]], "context": art[max(0, f["start"] - 50):f["end"] + 30].replace("\n", " ")}
            if any(z[2] in ("quote", "marked") for z in hit):
                pairs_true.append(row)
            elif any(z[2] == "allusion" for z in hit):
                pairs_allusion.append(row)
            else:
                pairs_false.append({**row, "labelled_ordinary": any(z[2] == "ordinary" for z in hit)})
    missed = [g for g in gold2 if g not in found_any]
    return {"set": name, "articles": len(rows), "chars": chars,
            "two_word_quotes": len(gold2), "found_by_any_finding": len(found_any), "found_by_pair": len(found_pair),
            "pairs_on_quotes": len(pairs_true), "pairs_on_allusions": len(pairs_allusion), "pairs_false": len(pairs_false),
            "false_per_10k": round(len(pairs_false) / chars * 10_000, 2) if chars else None,
            "missed": missed, "false_items": pairs_false, "allusion_items": pairs_allusion, "true_items": pairs_true}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sets", nargs="+")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for spec in a.sets:
        name, rows = load(spec)
        r = score(name, rows)
        print(f"{name}: {r['articles']} articles, {r['chars']} chars | two-word quotes found {r['found_by_any_finding']}/{r['two_word_quotes']}"
              f" (by pair {r['found_by_pair']}) | pairs on quotes {r['pairs_on_quotes']}, on allusions {r['pairs_on_allusions']},"
              f" FALSE {r['pairs_false']} ({r['false_per_10k']}/10k)")
        if a.show:
            for x in r["false_items"]:
                print("   FALSE", x["case"], x["text"], "| …" + x["context"] + "…", "(labelled ordinary)" if x["labelled_ordinary"] else "")
            for x in r["allusion_items"]:
                print("   ALLUSION", x["case"], x["text"])
            for m in r["missed"]:
                print("   MISSED", *m)
        if not name.startswith("wiki"):
            out = ROOT / "eval" / "results" / f"short-pairs-{stamp}-{a.tag}-{name}.json"
        else:  # the Wikipedia text stays local: keep only counts and the surfaced pairs in the scratch directory
            out = Path(spec.split(":")[1]).parent / f"short-pairs-{stamp}-{a.tag}-{name}.json"
        out.write_text(json.dumps({"tag": a.tag, "params": _params(), **r}, ensure_ascii=False, indent=1), encoding="utf-8")


def _params() -> dict:
    from app import phrases
    return {k: getattr(phrases, k) for k in ("PAIR_RARE_ZIPF", "PAIR_OTHER_ZIPF", "PAIR_MAX_AYAHS")}


if __name__ == "__main__":
    main()
