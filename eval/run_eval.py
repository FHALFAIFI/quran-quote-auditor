"""Score the pipeline on the hand-labelled set (eval/cases.json).

    python eval/run_eval.py --mode fallback      # no AI (reduced mode), deterministic
    python eval/run_eval.py --mode ai            # uses the configured provider (GROQ_API_KEY / GEMINI_API_KEY);
                                                 # only valid if the AI actually responded on EVERY case
    python eval/run_eval.py --mode ai --cases eval/heldout.json --tag heldout-v2   # other case file / file-name tag
    (the model and prompt come from GROQ_MODEL / GROQ_REASONING_EFFORT / EXTRACTION_PROMPT, and are recorded)
    python eval/run_eval.py --mode ai --url https://<deployment> --pace 30   # audit through a deployed /api/audit;
                                                 # the provider and prompt are the server's, read from each response

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
from app import arabic  # noqa: E402
from app.references import Reference, parse_reference  # noqa: E402
from app.config import settings  # noqa: E402
from app.extraction.prompts import prompt_version  # noqa: E402
from app.verifier import verify  # noqa: E402

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


def grade_corrections(hit: dict, g: dict) -> dict:
    """Score the proposed (non-optional) corrections for one detected gold quotation.

    fix_ok: the corrected excerpt verifies as "matched" at the gold location (source-checked).
    false_fix: a wording/diacritics fix was proposed for a quote labelled correct (safety count).
    """
    fixes = [c for c in hit.get("changes", []) if not c["optional"]]
    wfix = next((c for c in fixes if c["kind"] in ("wording", "diacritics")), None)
    rfix = next((c for c in fixes if c["kind"] == "reference"), None)
    out = {"wording_fix": None, "reference_fix": None,
           "false_fix": bool(wfix) and g["wording"] == "correct",
           "false_reference_fix": bool(rfix) and g["reference"] in ("correct", "surah_only")}
    if wfix:
        index = audit.source.get()
        gold_ref = Reference(0, 0, "", g["surah"], g["ayah_start"], g["ayah_end"])
        words = [t.raw for t in arabic.tokenize(wfix["quote_after"])]
        res = verify(index, words, gold_ref)
        ok = res["wording"]["status"] == "matched" and arabic.folded(wfix["quote_after"]) == arabic.folded(g["correct_text"])
        out["wording_fix"] = "ok" if ok else "wrong"
    if rfix:
        r = parse_reference(rfix["replacement"])
        ok = r is not None and (r.surah, r.ayah_start, r.ayah_end or r.ayah_start) == (g["surah"], g["ayah_start"], g["ayah_end"])
        out["reference_fix"] = "ok" if ok else "wrong"
    return out


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
    ap.add_argument("--cases", default=str(ROOT / "eval" / "cases.json"), help="labelled case file (never edited by this script)")
    ap.add_argument("--tag", default="", help="added to the result file name")
    ap.add_argument("--url", default="", help="send each article to <url>/api/audit instead of running in-process")
    ap.add_argument("--pace", type=float, default=0.0, help="seconds to wait between AI cases (Groq free tier: 8,000 tokens/min)")
    ap.add_argument("--retry-400", type=int, default=0, dest="retry_400",
                    help="in-process AI runs only: retry a case up to N times, but ONLY when the provider's error body identifies a model-generation "
                         "failure (strict-schema output that does not fit the schema). Any other 400 (a refused request), 429 and all other failures "
                         "still stop the run. Every retry is recorded with the error body")
    args = ap.parse_args()
    ai_quotes: dict[str, list] = {}
    if args.url:
        import httpx

        base = args.url.rstrip("/")
        health = httpx.get(base + "/api/health", timeout=90).json()
        print(f"Remote {base}: mode {health.get('mode')}, provider {health.get('provider')}")
        if args.mode == "ai" and not health.get("ai_configured"):
            print("NOT AN AI RUN: the server has no AI provider configured. Nothing recorded.")
            return 2

        def remote_audit(article: str) -> dict:
            r = httpx.post(base + "/api/audit", json={"article": article}, timeout=90)
            if r.status_code != 200:
                return {"mode": "http_error", "findings": [], "ai": {"responded": False, "outcome": f"http_{r.status_code}",
                                                                      "error": r.text[:200]}}
            return r.json()
        audit.run_audit = remote_audit
    elif args.mode == "fallback":
        audit.get_provider = lambda: None
    else:
        provider = audit.get_provider()
        if provider is None:
            print("NOT AN AI RUN: no AI provider is configured (set GROQ_API_KEY or GEMINI_API_KEY). Nothing recorded.")
            return 2
        print(f"AI provider: {provider.label}, prompt {prompt_version()}")
        extract = provider.extract

        def logged_extract(article: str):  # keep what the model proposed, for diagnosis
            out = extract(article)
            ai_quotes[article] = [{"quote": s.quote, "reference_text": s.reference_text} for s in out]
            return out
        provider.extract = logged_extract
        audit.get_provider = lambda: provider

    cases_path = Path(args.cases).resolve()
    data = json.loads(cases_path.read_text(encoding="utf-8"))
    rows, neg_hits, extra_findings, formula_hits, modes, timings, ai_log = [], [], [], [], Counter(), [], []
    for n_case, case in enumerate(data["cases"]):
        art = case["article"]
        if args.mode == "ai" and args.pace and n_case:
            time.sleep(args.pace)
        t = time.monotonic()
        retries = []
        while True:
            res = audit.run_audit(art)
            ai0 = res.get("ai") or {}
            if (args.mode == "ai" and not args.url and not ai0.get("responded") and ai0.get("http_status") == 400
                    and ai0.get("generation_failure") and len(retries) < args.retry_400):
                retries.append({"error": ai0.get("error"), "error_body": ai0.get("error_body"), "elapsed_ms": ai0.get("elapsed_ms")})
                audit.get_provider().tracker.clear_cooldown()  # the adapter starts a cooldown after any failure
                time.sleep(max(args.pace, 5.0))
                continue
            break
        timings.append(time.monotonic() - t)
        modes[res["mode"]] += 1
        ai = res.get("ai") or {}
        ai_log.append({"case": case["id"], "mode": res["mode"], **{k: ai.get(k) for k in (
            "provider", "model", "responded", "outcome", "http_status", "elapsed_ms", "proposed", "located", "discarded", "error",
            "error_body", "generation_failure")},
                       "model_quotes": ai_quotes.get(art), "retries_after_http_400": retries})
        if args.mode == "ai" and not ai.get("responded"):
            print(f"STOP: case {case['id']} fell back ({ai.get('outcome')}: {ai.get('error')}). "
                  "Not retrying and not recording an AI result.")
            print(json.dumps(ai_log, ensure_ascii=False, indent=1))
            stop = ROOT / "eval" / "results" / f"stopped-{datetime.now().strftime('%Y%m%d-%H%M%S')}{'-' + args.tag if args.tag else ''}.json"
            stop.write_text(json.dumps({"stopped_at": case["id"], "cases_file": str(cases_path.relative_to(ROOT)), "url": args.url or None,
                                        "prompt": prompt_version(), "ai_calls": ai_log}, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"saved {stop.relative_to(ROOT)} (not an AI result)")
            return 2
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
                det = hit.get("detection") or {}
                shown = [(b["surah"], b["ayah_start"], b["ayah_end"]) for b in ([src] if src else []) + [a["source"] for a in hit.get("alternatives", []) if a.get("source")]]
                row.update({
                    "detection_tier": det.get("tier"), "detection_kind": det.get("kind"),
                    # the gold verse is proposed, or (for repeated phrases) at least listed among the choices
                    "location_shown": (g["surah"], g["ayah_start"], g["ayah_end"]) in shown,
                    # a wrong verse offered as if confirmed (not as a mere possibility)
                    "false_confirmed_location": loc_ok is False and not det.get("unconfirmed"),
                    "detected_by": hit["detected_by"],
                    "wording_expected": w_exp, "wording_actual": w_act, "wording_level": hit["wording"]["level"],
                    "wording_grade": grade(w_act, w_exp),
                    "false_verified_wording": w_act == "matched" and g["wording"] != "correct",
                    "reference_expected": r_exp, "reference_actual": r_act, "reference_grade": grade(r_act, r_exp),
                    "false_verified_reference": r_act == "matched" and g["reference"] not in ("correct", "surah_only"),
                    "location_ok": loc_ok, "needs_review": hit["needs_review"],
                    "correction_status": hit.get("correction", {}).get("status"),
                    **grade_corrections(hit, g),
                })
            rows.append(row)
        for f in res["findings"]:
            if f["id"] in used:
                continue
            neg = next((n for n in case["negatives"] if overlap(f["start"], f["end"], art.index(n), art.index(n) + len(n)) > 0), None)
            frm = next((n for n in case.get("formulas", []) if overlap(f["start"], f["end"], art.index(n), art.index(n) + len(n)) > 0), None)
            det = f.get("detection") or {}
            entry = {"case": case["id"], "quote": f["quote"], "negative": neg or frm, "tier": det.get("tier"), "kind": det.get("kind"),
                     "wording": f["wording"]["status"], "presented_as_confirmed": not det.get("unconfirmed", False)}
            (formula_hits if frm and not neg else neg_hits if neg else extra_findings).append(entry)

    if args.mode == "ai" and (set(modes) != {"ai"} or not all(a["responded"] for a in ai_log)):
        print(f"NOT AN AI RESULT: modes observed {dict(modes)} — at least one case fell back. Nothing recorded as AI.")
        return 2

    det = [r for r in rows if r["detected"]]
    unm = [r for r in rows if "unmarked" in r["tags"]]
    unm_det = [r for r in unm if r["detected"]]
    summary = {
        "mode": args.mode,
        "cases_file": str(cases_path.relative_to(ROOT)),
        "url": args.url or None,
        "prompt": (None if args.url else prompt_version()) if args.mode == "ai" else None,
        "reasoning_effort": settings.groq_reasoning_effort or "(default)" if args.mode == "ai" else None,
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
        "formula_hits": len(formula_hits),
        "unmarked_detection": {
            "gold": len(unm), "detected": len(unm_det),
            "as_candidate": sum(r.get("detection_tier") == "candidate" for r in unm_det),
            "as_possible": sum(r.get("detection_tier") == "possible" for r in unm_det),
            "by_ai_or_marker": sum(r.get("detection_tier") in ("stated", "manual") for r in unm_det),
            "gold_verse_shown": sum(bool(r.get("location_shown")) for r in unm_det),
        },
        "false_suggestions": len(neg_hits) + len(formula_hits) + len(extra_findings),
        "false_confirmed": {
            # findings on non-Quran strings or everyday formulae that are presented as confirmed (not as "possible")
            "on_negatives_or_formulas": sum(h["presented_as_confirmed"] for h in neg_hits + formula_hits),
            "wrong_verse_as_confirmed": sum(bool(r.get("false_confirmed_location")) for r in det),
            "misquotation_reported_matched": sum(r["false_verified_wording"] for r in det),
            "on_other_unlabelled_text": sum(h["presented_as_confirmed"] for h in extra_findings),
        },
        "seconds_per_article_max": round(max(timings), 2),
        "seconds_per_article_mean": round(sum(timings) / len(timings), 2),
        "corrections": {
            "wording_errors_detected": sum(1 for r in det if r["wording_expected"] == "difference"),
            "wording_fix_ok": sum(r["wording_fix"] == "ok" for r in det),
            "wording_fix_wrong": sum(r["wording_fix"] == "wrong" for r in det),
            "wording_errors_review_only": sum(1 for r in det if r["wording_expected"] == "difference" and r["wording_fix"] is None),
            "reference_issues_detected": sum(1 for r in det if r["reference_expected"] in ("incorrect", "uncertain") and r["reference_actual"] != "missing"),
            "reference_fix_ok": sum(r["reference_fix"] == "ok" for r in det),
            "reference_fix_wrong": sum(r["reference_fix"] == "wrong" for r in det),
            "reference_issues_review_only": sum(1 for r in det if r["reference_expected"] in ("incorrect", "uncertain") and r["reference_actual"] != "missing" and r["reference_fix"] is None),
            "FALSE_wording_fix_on_correct_quote": sum(r["false_fix"] for r in det),
            "FALSE_reference_fix_on_correct_reference": sum(r["false_reference_fix"] for r in det),
        },
        "ai_models": sorted({a["model"] for a in ai_log if a["model"]}),
        "ai_cases_retried_after_400": sum(bool(a.get("retries_after_http_400")) for a in ai_log),
        "ai_candidates_proposed": sum(a["proposed"] or 0 for a in ai_log),
        "ai_candidates_discarded": sum(a["discarded"] or 0 for a in ai_log),
    }
    by_tag = defaultdict(lambda: [0, 0])
    for r in rows:
        for t in r["tags"]:
            by_tag[t][1] += 1
            by_tag[t][0] += r["detected"]
    summary["detection_by_tag"] = {t: f"{d}/{n}" for t, (d, n) in sorted(by_tag.items())}

    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(exist_ok=True)
    tag = f"-{args.tag}" if args.tag else ""
    out = out_dir / f"{args.mode}-{datetime.now().strftime('%Y%m%d-%H%M%S')}{tag}.json"
    out.write_text(json.dumps({"summary": summary, "ai_calls": ai_log, "rows": rows, "negative_hits": neg_hits, "formula_hits": formula_hits, "extra_findings": extra_findings}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for r in rows:
        if not r["detected"]:
            print(f"MISSED   {r['case']}: «{r['quote']}» tags={r['tags']}")
        elif r["wording_grade"] != "correct" or r["reference_grade"] != "correct" or r["location_ok"] is False:
            print(f"MISMATCH {r['case']}: «{r['quote']}» wording {r['wording_actual']} (exp {r['wording_expected']}), "
                  f"ref {r['reference_actual']} (exp {r['reference_expected']}), location_ok={r['location_ok']}")
    for r in rows:
        if r.get("wording_fix") == "wrong" or r.get("reference_fix") == "wrong" or r.get("false_fix") or r.get("false_reference_fix"):
            print(f"FIX-ISSUE {r['case']}: «{r['quote']}» wording_fix={r['wording_fix']} reference_fix={r['reference_fix']} "
                  f"false_fix={r['false_fix']} false_reference_fix={r['false_reference_fix']}")
    for n in neg_hits:
        print(f"NEG-HIT  {n['case']}: «{n['quote']}» tier={n['tier']} shown_as_confirmed={n['presented_as_confirmed']}")
    for n in formula_hits:
        print(f"FORMULA  {n['case']}: «{n['quote']}» tier={n['tier']} shown_as_confirmed={n['presented_as_confirmed']}")
    for e in extra_findings:
        print(f"EXTRA    {e['case']}: «{e['quote']}» tier={e['tier']} shown_as_confirmed={e['presented_as_confirmed']}")
    print(f"saved {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
