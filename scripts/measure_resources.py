"""Measure startup time and peak memory of the audit pipeline (no AI, no network).

    python scripts/measure_resources.py [--json out.json]

Each measurement runs in a FRESH child process, so peak RSS is that of one cold server
instance that loads the Quranpedia Hafs text from the local disk cache and audits articles.
The cache file must already exist (run the app or an evaluation once); this script never
downloads anything. Phases reported, per process:

  import_s        importing the application modules
  index_load_s    building the in-memory Quran index from the cached text (the "startup" cost
                  a cold Render instance pays once, apart from the one Quranpedia download)
  first_audit_s   first audit after the index is loaded
  rss_*_mb        current resident set size after each phase (from ``ps``)
  peak_rss_mb     peak RSS of the whole process (resource.ru_maxrss)

Workloads: every article of the evaluation sets, plus two 6,000-character worst cases
(an unmarked run of real mushaf text, and a soup of the most frequent Quran words).
The numbers describe THIS machine and Python, not Render; see docs/EVALUATION.md.

    python scripts/measure_resources.py --server [--json out.json]

``--server`` measures what Render actually runs: a real ``uvicorn app.main:app`` process (FastAPI, Starlette and
pydantic included), started fresh under ``/usr/bin/time -l`` so the OS reports its true peak resident set size
(macOS/BSD output format). It answers /api/health, then audits every evaluation article, the two 6,000-character
worst cases and 30 more articles in a row over HTTP, with the AI provider disabled, and reports time to the first
answered audit (server start + reading the cached Quran text + index build) and the peak RSS at shutdown.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHILD = "--child"


def rss_mb() -> float:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True).stdout.strip()
    return round(int(out) / 1024, 1)


def peak_mb() -> float:
    v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(v / (1024 * 1024) if sys.platform == "darwin" else v / 1024, 1)


def child() -> None:
    sys.path.insert(0, str(ROOT))
    res: dict = {"python": platform.python_version(), "platform": platform.platform()}
    t = time.perf_counter()
    import app.audit as audit  # noqa: E402
    from app.quran_source import source  # noqa: E402

    audit.get_provider = lambda: None  # deterministic path only
    res["import_s"] = round(time.perf_counter() - t, 3)
    res["rss_after_import_mb"] = rss_mb()

    t = time.perf_counter()
    idx = source.get()
    res["index_load_s"] = round(time.perf_counter() - t, 3)
    res["index_loaded_from"] = idx.loaded_from
    res["rss_after_index_mb"] = rss_mb()

    articles: list[tuple[str, str]] = []
    for name in ("cases.json", "heldout.json", "phrases_frozen.json"):
        p = ROOT / "eval" / name
        if p.exists():
            for c in json.loads(p.read_text(encoding="utf-8"))["cases"]:
                articles.append((f"{name}:{c['id']}", c["article"]))
    ayahs = [idx.ayahs[k].text for k in sorted(idx.ayahs)]
    run = " ".join(a for a in ayahs[280:400])[:6000]  # one long run of real mushaf text, no brackets
    words = sorted(idx.doc_freq, key=lambda w: -idx.doc_freq[w])[:60]
    soup, k = [], 0
    while sum(len(w) + 1 for w in soup) < 5900:
        soup.append(words[(k * 7) % len(words)])
        k += 1
    worst = [("worst:unmarked-mushaf-run", run), ("worst:frequent-word-soup", " ".join(soup))]

    timings, first = [], None
    for label, art in articles:
        t = time.perf_counter()
        audit.run_audit(art)
        dt = time.perf_counter() - t
        first = first if first is not None else dt
        timings.append(dt)
    res["first_audit_s"] = round(first, 3) if first is not None else None
    res["articles"] = len(timings)
    res["audit_mean_s"] = round(sum(timings) / len(timings), 4)
    res["audit_max_s"] = round(max(timings), 4)
    res["rss_after_eval_articles_mb"] = rss_mb()
    res["worst_case"] = {}
    for label, art in worst:
        t = time.perf_counter()
        r = audit.run_audit(art)
        res["worst_case"][label] = {"chars": len(art), "seconds": round(time.perf_counter() - t, 3), "findings": len(r["findings"])}
    res["rss_end_mb"] = rss_mb()
    res["peak_rss_mb"] = peak_mb()
    print(json.dumps(res, ensure_ascii=False))


def server_run(port: int = 8765) -> dict:
    import signal
    import urllib.request

    env = dict(os.environ, AI_PROVIDER="none", GROQ_API_KEY="", GEMINI_API_KEY="", RATE_LIMIT_PER_MINUTE="1000000")  # measurement only: no AI calls, no throttling
    t0 = time.perf_counter()
    proc = subprocess.Popen(["/usr/bin/time", "-l", sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

    def call(path: str, payload: dict | None = None) -> dict:
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())

    try:
        while True:  # wait for the port
            try:
                call("/api/health")
                break
            except OSError:
                if proc.poll() is not None or time.perf_counter() - t0 > 60:
                    raise RuntimeError("server did not start")
                time.sleep(0.05)
        t_health = time.perf_counter() - t0
        articles: list[str] = []
        for name in ("cases.json", "heldout.json", "phrases_frozen.json"):
            p = ROOT / "eval" / name
            if p.exists():
                articles += [c["article"] for c in json.loads(p.read_text(encoding="utf-8"))["cases"]]
        first = None
        times = []
        for art in articles:
            t = time.perf_counter()
            call("/api/audit", {"article": art})
            dt = time.perf_counter() - t
            if first is None:
                first = time.perf_counter() - t0  # process start → first audit answered
            times.append(dt)
        sample = json.loads((ROOT / "eval" / "phrases_frozen.json").read_text(encoding="utf-8"))["cases"][0]["article"]
        for _ in range(30):
            call("/api/audit", {"article": sample})
        worst = {}
        idx_text = json.loads((Path(tempfile_dir()) / "quran-auditor-cache" / "hafs-mushaf-1.json").read_text(encoding="utf-8"))["ayahs"]
        run = " ".join(a["text"] for a in idx_text[280:400])[:6000]
        t = time.perf_counter()
        call("/api/audit", {"article": run})
        worst["unmarked-mushaf-run"] = round(time.perf_counter() - t, 3)
        rss_live = None
        try:
            kids = subprocess.run(["pgrep", "-P", str(proc.pid)], capture_output=True, text=True).stdout.split()  # the python child of /usr/bin/time
            out = subprocess.run(["ps", "-o", "rss=", "-p", kids[0] if kids else str(proc.pid)], capture_output=True, text=True).stdout.strip()
            rss_live = round(int(out) / 1024, 1) if out else None
        except (ValueError, OSError):
            pass
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            err = proc.communicate(timeout=30)[1]
        except subprocess.TimeoutExpired:
            proc.kill()
            err = proc.communicate()[1]
    peak = None
    for line in err.splitlines():
        if "maximum resident set size" in line:
            peak = round(int(line.split()[0]) / (1024 * 1024), 1)  # bytes on macOS
    return {"seconds_to_health": round(t_health, 2), "seconds_to_first_audit": round(first, 2), "audits": len(times) + 31,
            "audit_mean_s": round(sum(times) / len(times), 4), "audit_max_s": round(max(times), 3), "worst_case_s": worst,
            "rss_after_all_mb": rss_live, "peak_rss_mb": peak, "python": platform.python_version()}


def tempfile_dir() -> str:
    import tempfile

    return tempfile.gettempdir()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", action="store_true", help="measure a real uvicorn process instead of an in-process audit")
    ap.add_argument("--json", default="", help="write the runs to this file")
    ap.add_argument("--runs", type=int, default=3, help="fresh processes to measure")
    ap.add_argument("--label", default="", help="free-text label stored with the result (e.g. the commit)")
    ap.add_argument(CHILD, action="store_true")
    args = ap.parse_args()
    if args.child:
        child()
        return 0
    if args.server:
        runs = [server_run() for _ in range(args.runs)]
        med = lambda key: sorted(r[key] for r in runs)[len(runs) // 2]  # noqa: E731
        summary = {k: med(k) for k in ("seconds_to_health", "seconds_to_first_audit", "audit_mean_s", "audit_max_s", "rss_after_all_mb", "peak_rss_mb")}
        print(f"uvicorn server, median of {len(runs)} fresh processes ({runs[0]['python']}, {platform.system()}):")
        print(json.dumps(summary, indent=1))
        print("worst case (last run):", runs[-1]["worst_case_s"])
        if args.json:
            Path(args.json).write_text(json.dumps({"label": args.label, "mode": "server", "summary": summary, "runs": runs}, ensure_ascii=False, indent=1), encoding="utf-8")
            print("saved", args.json)
        return 0
    runs = []
    for _ in range(args.runs):
        out = subprocess.run([sys.executable, __file__, CHILD], capture_output=True, text=True, cwd=ROOT)
        if out.returncode:
            print(out.stderr[-2000:])
            return 1
        runs.append(json.loads(out.stdout.strip().splitlines()[-1]))
    med = lambda key: sorted(r[key] for r in runs)[len(runs) // 2]  # noqa: E731
    summary = {k: med(k) for k in ("import_s", "index_load_s", "first_audit_s", "audit_mean_s", "audit_max_s",
                                   "rss_after_import_mb", "rss_after_index_mb", "rss_end_mb", "peak_rss_mb")}
    print(f"median of {len(runs)} fresh processes ({runs[0]['python']}, {platform.system()}):")
    print(json.dumps(summary, indent=1))
    print("worst cases (last run):", json.dumps(runs[-1]["worst_case"], ensure_ascii=False))
    if args.json:
        Path(args.json).write_text(json.dumps({"label": args.label, "summary": summary, "runs": runs}, ensure_ascii=False, indent=1), encoding="utf-8")
        print("saved", args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
