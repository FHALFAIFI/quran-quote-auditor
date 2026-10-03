"""Run a frozen suggestion set (eval/suggest_cases_*.json) against app.suggest and score it. No network call but the one that
loads the Quranpedia text (cached), no AI.

    python eval/run_suggest_eval.py eval/suggest_cases_20261003.json --tag first-run [--out eval/results]

The file is checked against its SHA-256 sidecar when one exists (eval/<name>.sha256); a mismatch stops the run.

Judging (per case, from the labels' `expect` block; nothing here is tuned to a set):

  expected "suggest" (not none_acceptable, not must_be_ambiguous)
      hit            status suggest AND the best choice's kind is in expect.kind AND its place is a gold place AND its proposed
                     words start with the gold words (complete_word: the whole word or its missing suffix) AND, when the label
                     demands it, the certainty is the expected one.
      wrong_place    a suggestion was made but none of its choices is at a gold place        (a FALSE suggestion)
      wrong_words    a gold place is offered but the best choice's words are not the gold words, or the kind/certainty differ
      missed         status none / hint
  expected "suggest" with must_be_ambiguous / none_acceptable (ambiguous openings, repeated verses)
      ok_none        nothing was suggested
      ok_choices     several places were offered, flagged ambiguous, none of them presented as a single exact choice
      false_confident  ONE place offered with certainty "exact" although the gold lists several places
      wrong_place    a suggestion none of whose choices is at a gold place
  expected "none"
      ok             status in expect.ok_status (none or hint)
      false_suggestion  status suggest
  Headline numbers are reported separately: detection (hit rate), false suggestions on none cases, false confident/wrong-place
  suggestions overall, correction quality (replace/insert cases only), ambiguity handling, and latency of the lookup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import arabic  # noqa: E402
from app.quran_source import source  # noqa: E402
from app.suggest import suggest  # noqa: E402


def fold_words(text: str) -> list[str]:
    return [t.fold for t in arabic.tokenize(text)]


def gold_words(index, gw) -> list[str] | None:
    if not gw:
        return None
    s, a, w0, w1 = gw
    return [f for w in index.ayahs[(s, a)].words[w0:w1] for f in fold_words(w)]


def check_sha(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    side = path.with_suffix(".sha256")
    if side.exists():
        want = side.read_text().split()[0].lower()
        if want != digest:
            raise SystemExit(f"{path.name}: SHA-256 {digest} does not match {side.name} ({want}); the frozen set was changed")
        return digest + " (matches " + side.name + ")"
    return digest + " (no sidecar file)"


def place_of(ch) -> tuple[int, int, int]:
    return (ch["surah"], ch["ayah_start"], ch["ayah_end"])


def words_ok(ch, want: list[str] | None, kind_expected: list[str]) -> bool:
    if want is None:
        return True
    proposed = fold_words(ch["to_text"] or ch["insert_text"])
    need = want
    if proposed[: len(need)] == need:
        return True
    if "complete_word" in kind_expected and len(need) == 1 and proposed:  # the missing suffix of a word being typed
        return need[0].endswith(proposed[0]) or proposed[0] == need[0]
    return False


def judge(case, res, index) -> dict:
    ex = case["expect"]
    status = res["status"]
    choices = res["choices"]
    gold_places = {tuple(p) for p in ex.get("gold_places") or []}
    gw = gold_words(index, ex.get("gold_words"))
    out = {"id": case["id"], "category": case["category"], "expect": ex["outcome"], "status": status, "reason": res.get("reason"),
           "n_choices": len(choices), "ambiguous": bool(res.get("ambiguous")), "best": None}
    if choices:
        b = choices[0]
        out["best"] = {"kind": b["kind"], "certainty": b["certainty"], "label": b["label"], "to": b["to_text"]}
    amb = ex.get("must_be_ambiguous") or ex.get("none_acceptable")
    if ex["outcome"] == "none":
        out["verdict"] = "false_suggestion" if status == "suggest" else "ok"
        return out
    if amb:
        if status != "suggest":
            out["verdict"] = "ok_none"
        else:
            offered = {place_of(c) for c in choices}
            if not offered & gold_places:
                out["verdict"] = "wrong_place"
            elif len(offered) == 1 and choices[0]["certainty"] == "exact" and len(gold_places) > 1:
                out["verdict"] = "false_confident"
            elif len(offered) >= 2 and res.get("ambiguous"):
                out["verdict"] = "ok_choices"
            else:
                out["verdict"] = "false_confident"
        return out
    if status != "suggest":
        out["verdict"] = "missed"
        return out
    at_gold = [c for c in choices if place_of(c) in gold_places]
    if not at_gold:
        out["verdict"] = "wrong_place"
        return out
    b = choices[0]
    kind_ok = b["kind"] in ex.get("kind", [])
    cert_ok = ex.get("certainty") is None or b["certainty"] == ex["certainty"]
    if place_of(b) in gold_places and kind_ok and cert_ok and words_ok(b, gw, ex.get("kind", [])):
        out["verdict"] = "hit"
    else:
        out["verdict"] = "wrong_words"
        out["why"] = {"kind_ok": kind_ok, "cert_ok": cert_ok, "place_ok": place_of(b) in gold_places}
    return out


def summarise(rows) -> dict:
    by = defaultdict(Counter)
    for r in rows:
        by[r["category"]][r["verdict"]] += 1
    exp_s = [r for r in rows if r["expect"] == "suggest" and r["category"] not in ("ambiguous_opening", "repeated_verses")]
    exp_n = [r for r in rows if r["expect"] == "none"]
    amb = [r for r in rows if r["category"] in ("ambiguous_opening", "repeated_verses")]
    corr = [r for r in rows if r["category"] in ("wrong_word_replace", "missing_word_insert")]
    cnt = lambda rs, v: sum(1 for r in rs if r["verdict"] == v)
    pct = lambda a, b: round(100.0 * a / b, 1) if b else None
    return {
        "cases": len(rows),
        "detection": {"expected_suggest": len(exp_s), "hit": cnt(exp_s, "hit"), "hit_pct": pct(cnt(exp_s, "hit"), len(exp_s)),
                      "missed": cnt(exp_s, "missed"), "wrong_words": cnt(exp_s, "wrong_words"), "wrong_place": cnt(exp_s, "wrong_place")},
        "false_suggestions_on_none_cases": {"cases": len(exp_n), "false": cnt(exp_n, "false_suggestion"), "false_pct": pct(cnt(exp_n, "false_suggestion"), len(exp_n)),
                                            "ids": [r["id"] for r in exp_n if r["verdict"] == "false_suggestion"]},
        "ambiguity": {"cases": len(amb), "ok_none": cnt(amb, "ok_none"), "ok_choices": cnt(amb, "ok_choices"), "false_confident": cnt(amb, "false_confident"),
                      "wrong_place": cnt(amb, "wrong_place"), "ids_false_confident": [r["id"] for r in amb if r["verdict"] == "false_confident"]},
        "correction_quality": {"cases": len(corr), "hit": cnt(corr, "hit"), "hit_pct": pct(cnt(corr, "hit"), len(corr)),
                               "missed": cnt(corr, "missed"), "wrong_words": cnt(corr, "wrong_words"), "wrong_place": cnt(corr, "wrong_place"),
                               "presented_as_exact": sum(1 for r in corr if r["best"] and r["best"]["certainty"] == "exact")},
        "wrong_place_suggestions_anywhere": sum(1 for r in rows if r["verdict"] == "wrong_place"),
        "by_category": {k: dict(v) for k, v in sorted(by.items())},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", type=Path)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "eval" / "results")
    a = ap.parse_args()
    sha = check_sha(a.cases)
    data = json.loads(a.cases.read_text(encoding="utf-8"))
    index = source.get()
    rows, times = [], []
    for c in data["cases"]:
        t = time.perf_counter()
        res = suggest(index, c["before"], c.get("after", ""), explicit=c.get("explicit", False), distinct=c.get("distinct", False))
        times.append((time.perf_counter() - t) * 1000)
        rows.append(judge(c, res, index))
    summ = summarise(rows)
    times.sort()
    summ["lookup_ms"] = {"median": round(statistics.median(times), 2), "p95": round(times[int(0.95 * (len(times) - 1))], 2), "max": round(times[-1], 2)}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = a.out / f"suggest-{stamp}-{a.cases.stem}-{a.tag}.json"
    path.write_text(json.dumps({"set": a.cases.name, "sha256": sha, "tag": a.tag, "ran_at": stamp, "summary": summ, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False, indent=1))
    bad = [r for r in rows if r["verdict"] not in ("hit", "ok", "ok_none", "ok_choices")]
    print(f"\n{len(bad)} cases not ok:")
    for r in bad:
        print(f"  {r['id']} {r['category']}: {r['verdict']} (status {r['status']}/{r['reason']}, best {r['best']})")
    print("\nwrote", path)


if __name__ == "__main__":
    main()
