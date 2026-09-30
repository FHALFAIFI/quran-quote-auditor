"""Does a smaller max_completion_tokens avoid Groq's 1,000 output-tokens/minute (OTPM) 429s,
and does complete, schema-valid JSON still come back?

    python eval/experiments/token_reservation.py 4096 1024 512 256 [--gap 65]

For each reservation, sends every case of eval/cases.json and eval/heldout.json back-to-back
(no pacing), with the app's exact request except max_completion_tokens. Records per call: HTTP
status, the OTPM "Requested" figure from a 429 body, finish_reason, completion tokens, and
whether the content parses with the app's own parser. Waits --gap seconds between reservations
so each starts with an empty minute window. Diagnosis only; nothing here is scored.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.config import groq_api_key, settings  # noqa: E402
from app.extraction.base import ExtractionError  # noqa: E402
from app.extraction.gemini import parse_model_json  # noqa: E402
from app.extraction.groq import ENDPOINT, build_request  # noqa: E402
from app.extraction.prompts import prompt_version  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("reservations", nargs="+", type=int)
    ap.add_argument("--gap", type=float, default=65.0)
    args = ap.parse_args()
    key = groq_api_key()
    if not key:
        print("GROQ_API_KEY not set")
        return 2
    cases = []
    for f in ("cases.json", "heldout.json"):
        cases += json.loads((ROOT / "eval" / f).read_text(encoding="utf-8"))["cases"]
    model, pv = settings.groq_model, prompt_version()
    out = []
    for n, limit in enumerate(args.reservations):
        if n:
            time.sleep(args.gap)
        for c in cases:
            body = build_request(model, c["article"])
            body["max_completion_tokens"] = limit
            t = time.monotonic()
            r = httpx.post(ENDPOINT, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=30)
            ms = int((time.monotonic() - t) * 1000)
            j = r.json()
            choice = (j.get("choices") or [{}])[0]
            content = choice.get("message", {}).get("content")
            err = (j.get("error") or {}).get("message", "")
            requested = re.search(r"Requested (\d+)", err or "")
            parsed = None
            if isinstance(content, str):
                try:
                    parsed = len(parse_model_json(content, settings.max_candidates))
                except ExtractionError:
                    parsed = "invalid"
            rec = {"reservation": limit, "case": c["id"], "http_status": r.status_code, "elapsed_ms": ms,
                   "finish_reason": choice.get("finish_reason"), "usage": j.get("usage"),
                   "candidates_parsed": parsed, "otpm_requested": int(requested.group(1)) if requested else None,
                   "error": re.sub(r"org_\w+", "org_<redacted>", err)[:300] or None}
            out.append(rec)
            u = rec["usage"] or {}
            print(limit, c["id"][:14], r.status_code, rec["finish_reason"], u.get("prompt_tokens"),
                  u.get("completion_tokens"), parsed, rec["otpm_requested"], flush=True)
    d = ROOT / "eval" / "experiments" / "raw"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-reservation-{model.replace('/', '_')}-{pv}.json"
    f.write_text(json.dumps({"model": model, "prompt": pv, "calls": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", f.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
