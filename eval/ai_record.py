"""Record what the configured model proposes for each article, ONE call per article, for a later paired replay.

    GROQ_MAX_COMPLETION_TOKENS=800 python eval/ai_record.py --out <private dir> --cases eval/cases.json [--cases ...] \
        [--pace 65] [--max-calls 80]

Why record and replay: the model's answer does not depend on the detection code, so each article is sent once and the
audit is then computed with and without that same answer (eval/ai_contribution.py), on any code version, with no
further call. This keeps the Groq budget small and makes the comparison exact (same input, same code, one variable).

Call discipline (Groq free plan for qwen/qwen3.8-27b, read 4 Oct 2026 on console.groq.com/docs/rate-limits: 30 requests/min,
1,000/day, 8,000 tokens/min, 200,000 tokens/day; our account's error bodies also named 1,000 output tokens/min, which is why
the reservation is 800 and calls are at least 65 s apart): one attempt per article, no retry on any failure, the provider's own
cooldown honoured, and the run stops after two consecutive HTTP 429s, after any 401/403, or at --max-calls.

What is written (to --out, which must be OUTSIDE the repository): per call the article id, the outcome, HTTP status, latency,
token usage and rate-limit headers, the raw proposals, and the provider's error body. Article text is not copied there
(it is in the labelled set already); the key is never written.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from app.extraction import ExtractionError, get_provider  # noqa: E402
from app.extraction.prompts import prompt_version  # noqa: E402

_last: dict = {}
_orig_post = httpx.Client.post


def _spy_post(self, url, *a, **kw):  # keeps status, usage and rate-limit headers of the provider's own call
    t = time.monotonic()
    resp = _orig_post(self, url, *a, **kw)
    _last.clear()
    _last.update(status=resp.status_code, wall_ms=int((time.monotonic() - t) * 1000),
                 headers={k: v for k, v in resp.headers.items() if k.lower().startswith(("x-ratelimit", "retry-after"))})
    try:
        body = resp.json()
        _last["usage"] = body.get("usage")
        _last["model"] = body.get("model")
        _last["finish_reason"] = (body.get("choices") or [{}])[0].get("finish_reason")
    except ValueError:
        pass
    return resp


def articles(paths: list[str]):
    for p in paths:
        path = Path(p)
        if path.is_dir():  # the demonstration samples
            for f in sorted(path.glob("*.txt")):
                yield f"samples/{f.stem}", f.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for c in data["cases"]:
            yield f"{path.stem}/{c['id']}", c["article"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cases", action="append", required=True)
    ap.add_argument("--pace", type=float, default=65.0)
    ap.add_argument("--max-calls", type=int, default=80)
    ap.add_argument("--max-chars", type=int, default=6000, help="the service's model limit: longer articles are not sent")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    if ROOT in out.parents or out == ROOT:
        print("refusing: --out must be outside the repository")
        return 2
    out.mkdir(parents=True, exist_ok=True)
    provider = get_provider()
    if provider is None:
        print("no provider configured; nothing recorded")
        return 2
    httpx.Client.post = _spy_post
    log_path = out / f"record-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"
    done = set()
    for f in out.glob("record-*.jsonl"):  # resume: never send an article twice
        for line in f.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("outcome") == "ok":
                done.add(r["id"])
    calls, consecutive_429 = 0, 0
    print(f"provider {provider.label}, prompt {prompt_version()}, reservation {os.environ.get('GROQ_MAX_COMPLETION_TOKENS')}, "
          f"already recorded {len(done)}; log {log_path}")
    for aid, art in articles(args.cases):
        if aid in done or len(art) > args.max_chars:
            continue
        if calls >= args.max_calls:
            print("max calls reached")
            break
        if calls:
            time.sleep(args.pace)
        wait = provider.tracker.cooldown_remaining()
        if wait:
            time.sleep(wait + 1)
        calls += 1
        _last.clear()
        rec = {"id": aid, "chars": len(art), "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "model_configured": provider.model, "prompt": prompt_version()}
        t = time.monotonic()
        try:
            sugs = provider.extract(art)
            rec.update(outcome="ok", proposals=[{"quote": s.quote, "reference_text": s.reference_text} for s in sugs])
        except ExtractionError as exc:
            rec.update(outcome="failed", error=str(exc), error_body=exc.body)
        rec.update(elapsed_ms=int((time.monotonic() - t) * 1000), http=dict(_last), tracker=provider.tracker.status())
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        status = _last.get("status")
        print(f"{calls:3d} {aid:40s} {rec['outcome']:6s} http={status} {rec['elapsed_ms']} ms "
              f"proposals={len(rec.get('proposals', []))} usage={(_last.get('usage') or {}).get('total_tokens')}", flush=True)
        consecutive_429 = consecutive_429 + 1 if status == 429 else 0
        if consecutive_429 >= 2 or status in (401, 403):
            print(f"stopping: {'two consecutive 429s' if consecutive_429 >= 2 else f'HTTP {status}'}")
            break
    print(f"calls made: {calls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
