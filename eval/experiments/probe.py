"""Send chosen cases to Groq with the app's exact request and save the raw responses.

    GROQ_MODEL=... EXTRACTION_PROMPT=v1 python eval/experiments/probe.py c11 c12 [--cases eval/cases.json]

For diagnosis only: saves the full response message (content and, if present, reasoning) and usage to
eval/experiments/raw/. Nothing here is scored; scoring is eval/run_eval.py.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.config import groq_api_key, settings  # noqa: E402
from app.extraction.groq import ENDPOINT, build_request  # noqa: E402
from app.extraction.prompts import prompt_version  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="+", help="case id prefixes, e.g. c11 c12")
    ap.add_argument("--cases", default=str(ROOT / "eval" / "cases.json"))
    args = ap.parse_args()
    key = groq_api_key()
    if not key:
        print("GROQ_API_KEY not set")
        return 2
    cases = [c for c in json.loads(Path(args.cases).read_text(encoding="utf-8"))["cases"]
             if any(c["id"].startswith(i) for i in args.ids)]
    model, pv = settings.groq_model, prompt_version()
    out = []
    for c in cases:
        body = build_request(model, c["article"])
        t = time.monotonic()
        r = httpx.post(ENDPOINT, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=30)
        ms = int((time.monotonic() - t) * 1000)
        j = r.json()
        msg = (j.get("choices") or [{}])[0].get("message", {})
        rec = {"case": c["id"], "http_status": r.status_code, "elapsed_ms": ms, "model": j.get("model", model),
               "prompt": pv, "reasoning_effort": body.get("reasoning_effort"),
               "finish_reason": (j.get("choices") or [{}])[0].get("finish_reason"),
               "content": msg.get("content"), "reasoning": msg.get("reasoning"),
               "usage": j.get("usage"), "error": j.get("error")}
        out.append(rec)
        print(json.dumps({k: rec[k] for k in ("case", "http_status", "elapsed_ms", "finish_reason", "content")}, ensure_ascii=False))
    d = ROOT / "eval" / "experiments" / "raw"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{model.replace('/', '_')}-{pv}.json"
    f.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", f.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
