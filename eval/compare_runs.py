"""Compare two result files of eval/run_eval.py row by row (timings ignored).

    python eval/compare_runs.py eval/results/<before>.json eval/results/<after>.json
    python eval/compare_runs.py --tags <before-tag> <after-tag>      # every set that has a result with both tags

Prints each gold row whose fields changed, the negative / formula / extra findings that appeared or disappeared, and
the summary fields that moved. Exit 0 when nothing changed, 1 otherwise. Nothing is hidden: a changed row is listed
whatever the direction of the change.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results"
IGNORE_SUMMARY = {"when", "seconds_per_article_max", "seconds_per_article_mean"}


def _key(row: dict) -> tuple:
    return row["case"], row["quote"]


def _fkey(f: dict) -> tuple:
    return f["case"], f["quote"], f.get("tier"), f.get("wording"), f.get("presented_as_confirmed")


def compare(a_path: Path, b_path: Path) -> int:
    a, b = (json.loads(p.read_text(encoding="utf-8")) for p in (a_path, b_path))
    changed = 0
    print(f"== {a_path.name}\n   {b_path.name}")
    arows = {_key(r): r for r in a["rows"]}
    brows = {_key(r): r for r in b["rows"]}
    for k in sorted(set(arows) | set(brows)):
        ra, rb = arows.get(k), brows.get(k)
        if ra is None or rb is None:
            print(f"  ROW {'added' if ra is None else 'removed'}: {k}")
            changed += 1
            continue
        diffs = {f: (ra.get(f), rb.get(f)) for f in sorted(set(ra) | set(rb)) if ra.get(f) != rb.get(f)}
        if diffs:
            changed += 1
            print(f"  ROW {k[0]} «{k[1]}»")
            for f, (x, y) in diffs.items():
                print(f"      {f}: {x!r} -> {y!r}")
    for group in ("negative_hits", "formula_hits", "extra_findings"):
        fa = {_fkey(f) for f in a.get(group, [])}
        fb = {_fkey(f) for f in b.get(group, [])}
        for k in sorted(fa - fb):
            print(f"  {group} GONE: {k}")
            changed += 1
        for k in sorted(fb - fa):
            print(f"  {group} NEW:  {k}")
            changed += 1
    sa, sb = a["summary"], b["summary"]
    for f in sorted(set(sa) | set(sb)):
        if f not in IGNORE_SUMMARY and sa.get(f) != sb.get(f):
            print(f"  summary {f}: {json.dumps(sa.get(f), ensure_ascii=False)} -> {json.dumps(sb.get(f), ensure_ascii=False)}")
    print(f"  {'IDENTICAL' if not changed else f'{changed} change(s)'}")
    return changed


def _by_tag(tag: str) -> dict[str, Path]:
    out = {}
    for p in sorted(RESULTS.glob(f"fallback-*-{tag}-*.json")):
        out[p.stem.split(f"-{tag}-", 1)[1]] = p
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--tags", nargs=2, metavar=("BEFORE", "AFTER"))
    args = ap.parse_args()
    total = 0
    if args.tags:
        before, after = (_by_tag(t) for t in args.tags)
        for name in sorted(set(before) & set(after)):
            total += compare(before[name], after[name])
        missing = sorted(set(before) ^ set(after))
        if missing:
            print(f"sets without both runs: {missing}")
    else:
        total = compare(Path(args.paths[0]), Path(args.paths[1]))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
