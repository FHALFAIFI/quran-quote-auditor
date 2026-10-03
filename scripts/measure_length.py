"""How long may an article be? Time, memory and response size of one audit at 6,000 ... 20,000 characters.

    python scripts/measure_length.py [--json out.json] [--runs 3]              # in-process, AI off, fresh process
    python scripts/measure_length.py --url https://host --json out.json        # a running server, over HTTP

Workloads (all built from files in this repository, nothing downloaded but the cached Quranpedia text):
  eval-concat   the articles of the older evaluation sets joined into one text: DENSE (many quotations per page), an upper bound
  mushaf-run    unmarked running text of the mushaf itself (the search's most expensive honest input)
  freq-soup     the most frequent Quran words in a row (pathological: stops at the search's work budget and says so)
  long-set      the articles of eval/articles_long_20261003.json when present (realistic long articles, 7,000-19,000 characters)

--url mode refuses a server with AI configured: benchmarks must not make repeated model calls. Numbers describe THIS machine (or the
URL you pass); they are not a promise for another host. Peak memory is the child process's own maximum RSS (in-process mode only).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LENGTHS = (6000, 10000, 15000, 20000)
CHILD = "--child"


def workloads(idx=None):
    arts = []
    for name in ("cases.json", "heldout.json", "phrases_frozen.json"):
        p = ROOT / "eval" / name
        if p.exists():
            arts += [c["article"] for c in json.loads(p.read_text(encoding="utf-8"))["cases"]]

    def concat(n):
        out, tot, i = [], 0, 0
        while tot < n:
            a = arts[i % len(arts)]
            out.append(a)
            tot += len(a) + 2
            i += 1
        return "\n\n".join(out)[:n]

    items = [("eval-concat", n, concat(n)) for n in LENGTHS]
    if idx is not None:
        ayahs = [idx.ayahs[k].text for k in sorted(idx.ayahs)]
        words = sorted(idx.doc_freq, key=lambda w: -idx.doc_freq[w])[:60]

        def soup(n):
            s, k = [], 0
            while sum(len(w) + 1 for w in s) < n:
                s.append(words[(k * 7) % 60])
                k += 1
            return " ".join(s)[:n]

        items += [("mushaf-run", n, " ".join(ayahs[280:700])[:n]) for n in LENGTHS]
        items += [("freq-soup", n, soup(n)) for n in LENGTHS]
    long_set = ROOT / "eval" / "articles_long_20261003.json"
    if long_set.exists():
        data = json.loads(long_set.read_text(encoding="utf-8"))
        for c in data["cases"]:
            items.append(("long-set:" + str(c.get("id", "?")), len(c["article"]), c["article"]))
    return items


def rss_mb() -> float:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True).stdout.strip()
    return round(int(out) / 1024, 1)


def child(runs: int) -> None:
    sys.path.insert(0, str(ROOT))
    import app.audit as audit
    from app.quran_source import source

    audit.get_provider = lambda: None
    idx = source.get()
    res = {"python": platform.python_version(), "platform": platform.platform(), "rss_after_index_mb": rss_mb(), "rows": []}
    for label, n, art in workloads(idx):
        times = []
        for _ in range(runs):
            t = time.perf_counter()
            r = audit.run_audit(art)
            times.append(time.perf_counter() - t)
        body = len(json.dumps(r, ensure_ascii=False).encode("utf-8"))
        res["rows"].append({"workload": label, "chars": len(art), "median_s": round(statistics.median(times), 3), "max_s": round(max(times), 3),
                            "findings": len(r["findings"]), "capped": r.get("candidates_capped", 0), "search_truncated": bool((r.get("phrases") or {}).get("truncated")),
                            "response_kb": round(body / 1024), "rss_mb": rss_mb()})
    res["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)
    print(json.dumps(res, ensure_ascii=False))


def http(url: str, runs: int, timeout: int = 240) -> dict:
    sys.path.insert(0, str(ROOT))
    from app.quran_source import source

    with urllib.request.urlopen(url.rstrip("/") + "/api/health", timeout=timeout) as health_response:
        health = json.load(health_response)
    if health.get("ai_configured"):
        raise SystemExit("--url benchmark requires a server without AI configured; use local in-process mode instead")
    idx = source.get()
    res = {"url": url, "timeout_s": timeout, "rows": []}
    for label, n, art in workloads(idx):
        times, last, raw, failed = [], None, b"", None
        for _ in range(runs):
            req = urllib.request.Request(url.rstrip("/") + "/api/audit", data=json.dumps({"article": art}, ensure_ascii=False).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
            t = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    raw = r.read()
                times.append(time.perf_counter() - t)
                last = json.loads(raw)
            except Exception as exc:  # a timeout or an HTTP error is a RESULT, not a crash
                failed = f"{type(exc).__name__}: {str(exc)[:80]} after {time.perf_counter() - t:.0f} s"
                break
            time.sleep(7)   # stay under the server's audit allowance (10 per minute)
        row = {"workload": label, "chars": len(art), "failed": failed}
        if last is not None:
            row.update({"median_s": round(statistics.median(times), 2), "max_s": round(max(times), 2), "findings": len(last["findings"]), "capped": last.get("candidates_capped", 0),
                        "ai_outcome": last["ai"]["outcome"], "response_kb": round(len(raw) / 1024), "server_elapsed_ms": last.get("elapsed_ms"),
                        "search_truncated": bool((last.get("phrases") or {}).get("truncated"))})
        res["rows"].append(row)
        print("ROW", json.dumps(row, ensure_ascii=False), flush=True)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--url", default="")
    ap.add_argument(CHILD, action="store_true")
    a = ap.parse_args()
    if a.child:
        child(a.runs)
        return 0
    if a.url:
        out = http(a.url, max(1, a.runs))
    else:
        p = subprocess.run([sys.executable, __file__, CHILD, "--runs", str(a.runs)], capture_output=True, text=True, cwd=ROOT)
        if p.returncode:
            print(p.stderr[-2000:])
            return 1
        out = json.loads(p.stdout.strip().splitlines()[-1])
    for r in out["rows"]:
        if r.get("failed"):
            print(f"{r['workload']:22s} {r['chars']:6d} chars  FAILED: {r['failed']}")
            continue
        print(f"{r['workload']:22s} {r['chars']:6d} chars  {r['median_s']:7.3f} s (max {r['max_s']:.3f})  findings {r['findings']:3d}  capped {r['capped']}  response {r['response_kb']:5d} KB"
              + (f"  rss {r['rss_mb']} MB" if "rss_mb" in r else "") + ("  [search budget reached]" if r.get("search_truncated") else ""))
    if "peak_rss_mb" in out:
        print("peak RSS of the process:", out["peak_rss_mb"], "MB")
    if a.json:
        Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print("saved", a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
