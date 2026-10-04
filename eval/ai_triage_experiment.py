"""Prototype (not in the product): can the model tell which «possible» phrases the writer meant as a quotation?

    # 1) list the «possible» items the current code shows on labelled sets (no model)
    python eval/ai_triage_experiment.py collect --cases eval/articles_frozen.json --cases ... --out <private dir>
    # 2) ask the model once per article about its items (paced; stops after two consecutive 429s)
    GROQ_MAX_COMPLETION_TOKENS=300 python eval/ai_triage_experiment.py ask --out <private dir> [--pace 65] [--max-calls N]
    # 3) score against the labels
    python eval/ai_triage_experiment.py score --out <private dir> [--tag t]

Why this role. The extraction role the product uses today proposes where quotations are; on every live and labelled run
recorded so far it added (almost) nothing that the source search had not already found. The audit's real burden on a writer
is the «possible» queue: phrases that match the Quran but may be ordinary prose (on the two labelled article sets, an exact
but common «possible» item was a real quotation 11 times in 26). A model might help here WITHOUT any authority over text: it
sees only the sentence around a phrase the source search already matched and answers quote / prose / unsure. Verse text,
references and corrections still come only from the source, and the item stays visible whatever the model says.

Decision rule, fixed BEFORE any call (4 Oct 2026, 21:0x Riyadh): the role is worth building only if, on the labelled
«possible» items, the model answers "prose" for at least half of the items that are not quotations AND answers "prose" for
at most one in ten of the items that are real quotations. Below that, a writer would be misled more than helped.

Privacy: only the sentence around each item is sent (at most 280 characters), not the whole article.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

import app.audit as audit  # noqa: E402
from app.config import groq_api_key, settings  # noqa: E402

ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
PROMPT_VERSION = "triage-v1"
SYSTEM = """You help an Arabic editor review an article. Each item below is a sentence from the article with one phrase between ⟦ and ⟧.
The phrase has the same (or nearly the same) words as a phrase of the Quran. Decide, from how the sentence uses it, whether the
writer is QUOTING the Quran there:
- "quote": the writer cites or recites the verse (it is presented as Quran, or reads as a recited verse inside the sentence).
- "prose": the words are the writer's own ordinary Arabic that happens to share wording with the Quran (an everyday expression,
  a description, a hadith, a proverb or a du'a).
- "unsure": the sentence does not let you decide.
Judge only the phrase between ⟦ ⟧. Do not write any Quran text, any correction or any explanation. Answer for every id."""

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "judgement": {"type": "string", "enum": ["quote", "prose", "unsure"]}},
        "required": ["id", "judgement"], "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False,
}


def _ov(a0, a1, b0, b1) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def _sentence(art: str, s: int, e: int, limit: int = 280) -> str:
    stops = ".!؟?\n"
    a = max((art.rfind(ch, 0, s) for ch in stops), default=-1) + 1
    b = min([i for i in (art.find(ch, e) for ch in stops) if i >= 0] or [len(art)])
    a, b = max(a, s - 140), min(b + 1, e + 140)
    return (art[a:s] + "⟦" + art[s:e] + "⟧" + art[e:b]).strip()[: limit + 2]


def collect(args) -> int:
    audit.get_provider = lambda: None
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    items = []
    for p in args.cases:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        for case in data["cases"]:
            art = case["article"]
            res = audit.run_audit(art)
            for f in res["findings"]:
                if not f["detection"]["unconfirmed"]:
                    continue
                gold = any(_ov(f["start"], f["end"], g.get("start", art.find(g["quote"])),
                               g.get("end", art.find(g["quote"]) + len(g["quote"]))) > 0 for g in case["gold"])
                items.append({"article": f"{Path(p).stem}/{case['id']}", "id": f"{case['id']}#{f['id']}", "quote": f["quote"],
                              "codes": f["detection"]["codes"], "label": "quote" if gold else "prose",
                              "context": _sentence(art, f["start"], f["end"])})
    (out / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(items)} items ({Counter(i['label'] for i in items)}) from {len({i['article'] for i in items})} articles")
    return 0


def ask(args) -> int:
    out = Path(args.out)
    items = json.loads((out / "items.json").read_text(encoding="utf-8"))
    log = out / "answers.jsonl"
    done = set()
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["outcome"] == "ok":
                done.add(r["article"])
    key = groq_api_key()
    if not key:
        print("no GROQ_API_KEY")
        return 2
    by_article: dict[str, list] = {}
    for it in items:
        by_article.setdefault(it["article"], []).append(it)
    calls, c429 = 0, 0
    for art, its in by_article.items():
        if art in done:
            continue
        if calls >= args.max_calls:
            break
        if calls:
            time.sleep(args.pace)
        calls += 1
        user = "\n".join(f"id={it['id']}: {it['context']}" for it in its)
        body = {"model": settings.groq_model, "temperature": 0, "max_completion_tokens": settings.groq_max_completion_tokens,
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                "response_format": {"type": "json_schema", "json_schema": {"name": "triage", "strict": True, "schema": SCHEMA}}}
        if settings.groq_model.startswith("qwen/"):
            body["reasoning_effort"] = "none"
        t = time.monotonic()
        rec = {"article": art, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "prompt": PROMPT_VERSION, "n_items": len(its)}
        try:
            r = httpx.post(ENDPOINT, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=20)
            rec.update(status=r.status_code, ms=int((time.monotonic() - t) * 1000),
                       headers={k: v for k, v in r.headers.items() if k.lower().startswith(("x-ratelimit", "retry-after"))})
            if r.status_code == 200:
                j = r.json()
                rec.update(outcome="ok", usage=j.get("usage"), model=j.get("model"),
                           answer=json.loads(j["choices"][0]["message"]["content"])["items"])
            else:
                err = (r.json().get("error") or {}) if r.headers.get("content-type", "").startswith("application/json") else {}
                rec.update(outcome="failed", error={k: str(err.get(k))[:200] for k in ("type", "code", "message")})
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            rec.update(outcome="failed", error={"type": type(exc).__name__})
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"{calls:3d} {art:40s} {rec['outcome']} {rec.get('status')} {rec.get('ms')} ms items={len(its)}", flush=True)
        c429 = c429 + 1 if rec.get("status") == 429 else 0
        if c429 >= 2 or rec.get("status") in (401, 403):
            print("stopping")
            break
    print(f"calls made: {calls}")
    return 0


def score(args) -> int:
    out = Path(args.out)
    items = {i["id"]: i for i in json.loads((out / "items.json").read_text(encoding="utf-8"))}
    answers: dict[str, str] = {}
    calls = Counter()
    for line in (out / "answers.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        calls[f"{r['outcome']}_{r.get('status')}"] += 1
        for a in r.get("answer") or []:
            answers[a["id"]] = a["judgement"]
    table = Counter((items[i]["label"], answers.get(i, "no_answer")) for i in items)
    prose = [i for i in items.values() if i["label"] == "prose"]
    quote = [i for i in items.values() if i["label"] == "quote"]
    prose_said_prose = sum(answers.get(i["id"]) == "prose" for i in prose)
    quote_said_prose = sum(answers.get(i["id"]) == "prose" for i in quote)
    rule = {"prose_items": len(prose), "prose_said_prose": prose_said_prose, "quote_items": len(quote), "quote_said_prose": quote_said_prose,
            "passes": bool(prose) and bool(quote) and prose_said_prose >= 0.5 * len(prose) and quote_said_prose <= 0.1 * len(quote)}
    res = {"prompt": PROMPT_VERSION, "calls": dict(calls), "confusion": {f"{a}->{b}": n for (a, b), n in sorted(table.items())}, "decision_rule": rule,
           "by_code": {}}
    for code in ("common", "approximate", "cue", "non_quran_cue"):
        sub = [i for i in items.values() if code in i["codes"]]
        res["by_code"][code] = dict(Counter((i["label"], answers.get(i["id"], "no_answer")) for i in sub).most_common())
        res["by_code"][code] = {f"{a}->{b}": n for (a, b), n in res["by_code"][code].items()}
    path = ROOT / "eval" / "results" / f"ai-triage-{datetime.now().strftime('%Y%m%d-%H%M%S')}{'-' + args.tag if args.tag else ''}.json"
    path.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"saved {path.relative_to(ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["collect", "ask", "score"])
    ap.add_argument("--cases", action="append", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--pace", type=float, default=65.0)
    ap.add_argument("--max-calls", type=int, default=30)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    return {"collect": collect, "ask": ask, "score": score}[args.step](args)


if __name__ == "__main__":
    sys.exit(main())
