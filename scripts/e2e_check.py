"""End-to-end check against a running instance (local or deployed).

    python scripts/e2e_check.py http://localhost:8000
    python scripts/e2e_check.py https://<app>.vercel.app
    python scripts/e2e_check.py http://127.0.0.1:8000 --excerpt   # a server holding only the 36-verse test excerpt (CI)

Runs the three sample articles and a few error cases, then prints what the
app returned. It reports observations only; it is not an accuracy evaluation.
Never prints secrets (the API key is not needed by this script).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

EXCERPT = False  # set by --excerpt
SAMPLES = Path(__file__).resolve().parent.parent / "app" / "static" / "samples"


def show_finding(f: dict) -> str:
    w, r = f["wording"], f["reference"]
    src = f["source"]["label"] if f["source"] else "—"
    ref = r["found"]["text"] if r["found"] else "—"
    diffs = [d for d in w.get("diff", []) if d["op"] != "equal"]
    extra = ""
    if diffs:
        extra += " diff=" + "; ".join(f"{d['op']}:{d['quote']}→{d['source']}" for d in diffs)
    if w.get("diacritic_conflicts"):
        extra += " diacritics=" + "; ".join(f"{d['quote']}→{d['source']}" for d in w["diacritic_conflicts"])
    return (f"  #{f['id']} L{f['line']} by={'+'.join(f['detected_by'])} «{f['quote']}»\n"
            f"      wording={w['status']}/{w['level']} source={src} | ref={r['status']} (written: {ref}, expected: {r['expected']})"
            f"{' | REVIEW' if f['needs_review'] else ''}{extra}")


def main(base: str) -> int:
    base = base.rstrip("/")
    failures = 0
    with httpx.Client(timeout=90) as c:
        t = time.monotonic()
        h = c.get(f"{base}/api/health")
        print(f"health {h.status_code} in {time.monotonic() - t:.2f}s: {json.dumps(h.json(), ensure_ascii=False)}")
        for sample in sorted(SAMPLES.glob("sample-*.txt")):
            text = sample.read_text(encoding="utf-8").strip()
            t = time.monotonic()
            res = c.post(f"{base}/api/audit", json={"article": text})
            dt = time.monotonic() - t
            print(f"\n=== {sample.name}: HTTP {res.status_code} in {dt:.2f}s")
            if res.status_code != 200:
                failures += 1
                print("  ", res.text[:300])
                continue
            data = res.json()
            print(f"  mode={data['mode']} provider={data['provider']} source_available={data['source']['available']} "
                  f"loaded_from={data['source'].get('loaded_from')} server_ms={data['elapsed_ms']}")
            ai = data.get("ai") or {}
            print(f"  ai: configured={ai.get('configured')} responded={ai.get('responded')} outcome={ai.get('outcome')} "
                  f"model={ai.get('model')} http={ai.get('http_status')} ms={ai.get('elapsed_ms')} "
                  f"proposed={ai.get('proposed')} located={ai.get('located')} discarded={ai.get('discarded')} error={ai.get('error')}")
            for n in data["notices"]:
                print(f"  notice[{n['level']}]: {n['text']}")
            for f in data["findings"]:
                print(show_finding(f))
                if text[f["start"]:f["end"]] != f["quote"]:
                    failures += 1
                    print("  !! quote does not match article offsets")
                for ch in f.get("changes", []):
                    print(f"      proposed {ch['kind']}{' (optional)' if ch['optional'] else ''}: «{ch['original']}» → «{ch['replacement']}» [{ch['label']}]")
                    if text[ch["start"]:ch["end"]] != ch["original"]:
                        failures += 1
                        print("  !! change does not match article offsets")
                if f.get("correction", {}).get("status") == "review_only" and f["needs_review"]:
                    print(f"      no automatic fix: {f['correction']['reason']}")
            print(f"  stats={data['stats']}")

        limit = c.get(f"{base}/api/health").json()["max_chars"]
        print("\n=== error handling")
        cases = [
            ("empty article", {"article": "  "}, 400),
            ("too long (limit + 1)", {"article": "ا" * (limit + 1)}, 400),
            ("wrong field", {"text": "x"}, 422),
            ("removed AI switch", {"article": "نص", "ai": False}, 422),
        ]
        for name, body, want in cases:
            r = c.post(f"{base}/api/audit", json=body)
            ok = r.status_code == want
            failures += not ok
            print(f"  {name}: HTTP {r.status_code} (expected {want}) {'OK' if ok else 'FAIL'} — {r.text[:120]}")
        r = c.post(f"{base}/api/audit", content=b"{not json", headers={"content-type": "application/json"})
        print(f"  malformed JSON body: HTTP {r.status_code} — {r.text[:120]}")
        failures += r.status_code != 422
        r = c.post(f"{base}/api/audit", json={"article": "<img src=x onerror=alert(1)> ﴿اقرأ باسم ربك الذي خلق﴾"})
        print(f"  markup in article: HTTP {r.status_code}; echoed article field: {'article' in r.json()}")
        # at the limit exactly: accepted; the model's shorter limit excludes this article
        r = c.post(f"{base}/api/audit", json={"article": ("قال تعالى: ﴿إن مع العسر يسرا﴾ [الشرح: 6]. " * 400)[:limit]}, timeout=120)
        ok = r.status_code == 200 and r.json()["ai"]["outcome"] in ("skipped_length", "not_configured")
        failures += not ok
        print(f"  article of exactly {limit} characters, beyond model limit: HTTP {r.status_code} {'OK' if ok else 'FAIL'}")
        print("\n=== verse suggestion and trust pages")
        # --excerpt: the server holds only the 36-verse test excerpt (CI), so the probe uses a verse that is in it
        before, want = ("قال تعالى: ﴿هل يستوي الذين يعلمون", "والذين لا يعلمون") if EXCERPT else ("قال تعالى: وما خلقت الجن والإنس إلا", "ليعبدون")
        r = c.post(f"{base}/api/suggest", json={"before": before, "request_id": 5})
        j = r.json()
        first = (j.get("choices") or [{}])[0].get("to_text")
        ok = r.status_code == 200 and j.get("request_id") == 5 and j.get("status") == "suggest" and first == want
        failures += not ok
        print(f"  /api/suggest: HTTP {r.status_code} status={j.get('status')} first={first} {'OK' if ok else 'FAIL'}")
        r = c.post(f"{base}/api/suggest", json={"before": "ا" * 5000})
        failures += r.status_code != 422
        print(f"  /api/suggest with 5000 characters: HTTP {r.status_code} (expected 422)")
        for path in ["/sources", "/privacy", "/limitations", "/roadmap"]:
            r = c.get(base + path)
            ok = r.status_code == 200 and "<h1>" in r.text and "قيد الإعداد" not in r.text
            failures += not ok
            print(f"  {path}: HTTP {r.status_code} {'OK' if ok else 'FAIL'}")
        print("\n=== files that must NOT be served")
        for path in ["/.env", "/.env.local", "/.env.example", "/app/config.py", "/requirements.txt", "/eval/cases.json",
                     "/tests/fixtures/hafs_subset.json", "/static/../app/config.py", "/static/%2e%2e/app/config.py", "/.git/config", "/.vercel/project.json"]:
            r = c.get(base + path)
            ok = r.status_code in (404, 400)
            failures += not ok
            print(f"  {path}: HTTP {r.status_code} {'OK' if ok else 'EXPOSED?'}")
    print(f"\nfailures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    EXCERPT = "--excerpt" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--excerpt"]
    sys.exit(main(args[0] if args else "http://localhost:8000"))
