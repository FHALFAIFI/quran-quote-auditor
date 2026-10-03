"""Builds eval/articles_long_20261003.json (+ its .sha256): 10 realistic LONG Arabic articles (7,000-19,000 characters)
with labelled Quran quotations. Written 3 Oct 2026 by an AI subagent (Claude) in a fresh context, from the Quranpedia
Hafs text and the contract of eval/validate_articles_long_20261003.py only (never from the detector's behaviour).
Quran words are cut from the Quranpedia text by coordinates (see eval/long_src_20261003/engine.py); the prose of each
article is hand-written in eval/long_src_20261003/a01_*.py ... a10_*.py.

    .venv/bin/python eval/build_articles_long_20261003.py [--freeze]      # run from the repo root
"""
import hashlib
import importlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from long_src_20261003.engine import build_case  # noqa: E402

MODULES = ["a01_knowledge", "a02_trade", "a03_technology", "a04_patience", "a05_family",
           "a06_environment", "a07_time", "a08_charity", "a09_neighbours", "a10_youth"]

ABOUT = open(HERE / "long_src_20261003" / "about.txt", encoding="utf-8").read().strip()


def main():
    mods = []
    for name in MODULES:
        try:
            mods.append(importlib.import_module(f"long_src_20261003.{name}"))
        except ModuleNotFoundError as e:
            if e.name != f"long_src_20261003.{name}":
                raise
            print("skipping (not written yet):", name, file=sys.stderr)
    cases = [build_case(m) for m in mods]
    out = HERE / "articles_long_20261003.json"
    text = json.dumps({"_about": ABOUT, "version": 1, "cases": cases}, ensure_ascii=False, indent=1)
    out.write_text(text, encoding="utf-8")
    for c in cases:
        print(c["id"], len(c["article"]), "chars,", len(c["gold"]), "gold")
    if "--freeze" in sys.argv:
        digest = hashlib.sha256(out.read_bytes()).hexdigest()
        (HERE / "articles_long_20261003.sha256").write_text(f"{digest}  eval/articles_long_20261003.json\n", encoding="utf-8")
        print("frozen:", digest)


if __name__ == "__main__":
    main()
