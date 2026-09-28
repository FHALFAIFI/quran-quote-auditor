"""End-to-end check against a running instance (local or deployed).

    python scripts/e2e_check.py http://localhost:8000
    python scripts/e2e_check.py https://<app>.vercel.app

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
            for n in data["notices"]:
                print(f"  notice[{n['level']}]: {n['text']}")
            for f in data["findings"]:
                print(show_finding(f))
                if text[f["start"]:f["end"]] != f["quote"]:
                    failures += 1
                    print("  !! quote does not match article offsets")
            print(f"  stats={data['stats']}")

        print("\n=== error handling")
        cases = [
            ("empty article", {"article": "  "}, 400),
            ("too long", {"article": "ا" * 7000}, 400),
            ("wrong field", {"text": "x"}, 422),
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
    print(f"\nfailures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"))
