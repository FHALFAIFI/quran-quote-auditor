"""Concurrent-audit load test (stdlib + httpx). LOCAL use only.

    python scripts/load_test.py                      # starts its own AI-off server, K=10 concurrent, 3 rounds, 6,000 characters
    python scripts/load_test.py --k 1 --rounds 10    # a sequential baseline
    python scripts/load_test.py --url http://127.0.0.1:8000 --k 10

Articles: the ten long evaluation articles (eval/articles_long_20261003.json, read only), each cut at the last space before
--chars characters. Every request is a real POST /api/audit; the latency is measured on the client from send to full answer.

It never runs against the live service: a URL on onrender.com is refused, any other non-local URL needs --allow-remote, and a server
whose /api/health says a model is configured is refused (each audit there would be a model call).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parent.parent


def articles(chars: int) -> list[str]:
    cases = json.loads((ROOT / "eval/articles_long_20261003.json").read_text(encoding="utf-8"))["cases"]
    out = []
    for c in cases:
        text = c["article"]
        if len(text) > chars:
            cut = text.rfind(" ", 0, chars)
            text = text[: cut if cut > chars * 0.9 else chars]
        out.append(text)
    return out


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(python: str, workers: int = 1) -> tuple[str, subprocess.Popen]:
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not (k.startswith(("GROQ_", "GEMINI_", "GOOGLE_")) or "API_KEY" in k)}
    env.update(AI_PROVIDER="none", RATE_LIMIT_PER_MINUTE="100000")
    cmd = [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"]
    if workers > 1:
        cmd += ["--workers", str(workers)]  # separate processes: each loads its own Quran index (memory x workers)
    proc = subprocess.Popen(cmd,
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            if httpx.get(base + "/api/health", timeout=1).status_code == 200:
                return base, proc
        except httpx.HTTPError:
            time.sleep(0.2)
    proc.kill()
    raise SystemExit("the local server did not start")


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, max(0, round(p / 100 * len(s) + 0.5) - 1))]  # nearest-rank


def one(client: httpx.Client, base: str, text: str, barrier: threading.Barrier | None) -> tuple[float, int, int]:
    if barrier:
        barrier.wait()
    t = time.perf_counter()
    try:
        r = client.post(base + "/api/audit", json={"article": text}, timeout=300)
        code = r.status_code
        n = len(r.json().get("findings", [])) if code == 200 else -1
    except httpx.HTTPError:
        code, n = 0, -1
    return time.perf_counter() - t, code, n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url")
    ap.add_argument("--allow-remote", action="store_true")
    ap.add_argument("--k", type=int, default=10, help="concurrent audits per round")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--chars", type=int, default=6000)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--workers", type=int, default=1, help="uvicorn worker processes for the local server (an experiment; production runs 1)")
    args = ap.parse_args()

    proc = None
    if args.url:
        base = args.url.rstrip("/")
        host = urlparse(base).hostname or ""
        if host.endswith("onrender.com"):
            raise SystemExit("refused: this script is not run against the live Render service")
        if host not in ("127.0.0.1", "localhost", "::1") and not args.allow_remote:
            raise SystemExit("refused: a non-local URL needs --allow-remote")
    else:
        base, proc = start_server(args.python, args.workers)
    try:
        health = httpx.get(base + "/api/health", timeout=10).json()
        if health.get("ai_configured"):
            raise SystemExit("refused: this server has a model configured (every audit would be a model call)")
        texts = articles(args.chars)
        with httpx.Client(limits=httpx.Limits(max_connections=max(args.k, 1) + 2)) as client:
            warm = one(client, base, texts[0], None)  # loads the Quran index; not counted
            for t in texts[: max(0, args.workers * 3)]:  # with several workers, warm each process (the OS picks which one answers)
                one(client, base, t, None)
            lat, codes, findings = [], [], []
            walls = []
            for r in range(args.rounds):
                barrier = threading.Barrier(args.k) if args.k > 1 else None
                t0 = time.perf_counter()
                with ThreadPoolExecutor(max_workers=args.k) as pool:
                    jobs = [pool.submit(one, client, base, texts[(r * args.k + i) % len(texts)], barrier) for i in range(args.k)]
                    for j in jobs:
                        dt, code, n = j.result()
                        lat.append(dt)
                        codes.append(code)
                        findings.append(n)
                walls.append(time.perf_counter() - t0)
        ok = [d for d, c in zip(lat, codes) if c == 200]
        summary = {
            "server": base if args.url else f"local, started by this script (AI_PROVIDER=none, workers={args.workers})",
            "python": sys.version.split()[0],
            "k": args.k, "rounds": args.rounds, "requests": len(lat),
            "article_chars": sorted({len(t) for t in texts}),
            "warmup_s": round(warm[0], 3),
            "errors": sum(1 for c in codes if c != 200), "status_codes": sorted(set(codes)),
            "p50_s": round(statistics.median(ok), 3) if ok else None,
            "p95_s": round(pct(ok, 95), 3) if ok else None,
            "max_s": round(max(ok), 3) if ok else None,
            "min_s": round(min(ok), 3) if ok else None,
            "round_wall_s": [round(w, 3) for w in walls],
            "findings_per_article": sorted(set(findings)),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=10)


if __name__ == "__main__":
    main()
