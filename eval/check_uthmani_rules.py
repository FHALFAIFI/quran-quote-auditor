"""How far the Uthmani rules (app/uthmani.py) reach, measured on whole Uthmani texts against the Quranpedia imla'i text.

    python eval/check_uthmani_rules.py [--exclude-heldout | --only-heldout] [--cache DIR]

Two Uthmani texts are compared word by word with the Quranpedia Hafs text (mushaf 1), verse by verse:
  tanzil      Tanzil Quran text, Uthmani v1.1 (Tanzil Project, https://tanzil.net; eval/tanzil_text.py)
  mushaf2     Quranpedia mushaf 2 (the King Fahd Complex Uthmani text edition)
Each text is downloaded once (one request each) and cached in DIR (default: the system temp directory; the Tanzil XML is cached
by eval/tanzil_text.py, or give its path in TANZIL_XML); nothing is committed. For each text it reports
  * verses whose every word is explained by the rules (``uthmani.explain``: identical letters, hamza seats included),
  * the words that are not, by frequency (the spellings the rules do not cover),
  * non-interference: words of the imla'i text itself that the Uthmani fold would change (must be 0),
  * vowel conflicts among the explained words.
``--exclude-heldout`` leaves out the verses of eval/uthmani_heldout.json (the rules were derived without them).
This is a measure of the rules on development data, not of end-to-end accuracy (that is eval/run_eval.py on the held-out set).
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import arabic, uthmani  # noqa: E402
from app.quran_source import source  # noqa: E402
from tanzil_text import load as load_tanzil  # noqa: E402  (eval/tanzil_text.py)

UA = {"User-Agent": "quran-quote-auditor-eval/0.1 (one request per text)"}


def fetch(url: str, path: Path) -> dict:
    if not path.exists():
        req = urllib.request.Request(url, headers=UA)
        path.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    return json.loads(path.read_text(encoding="utf-8"))


def words_of(text: str) -> list[str]:
    return [w for w in text.replace("﻿", "").split() if arabic.folded(w)]


def parts(word: str) -> list[str]:
    return [word[a:b] for a, b in uthmani.split_vocative(word)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exclude-heldout", action="store_true")
    ap.add_argument("--only-heldout", action="store_true")
    ap.add_argument("--cache", default=str(Path(tempfile.gettempdir()) / "quran-uthmani-check"))
    args = ap.parse_args()
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    idx = source.get()
    imlai = {f"{s}:{n}": a.text for (s, n), a in idx.ayahs.items()}
    tanzil = load_tanzil()
    m2 = fetch("https://api.quranpedia.net/v1/mushafs/2", cache / "quranpedia-mushaf-2.json")
    mushaf2 = {f"{int(s['id'])}:{int(x['number'])}": x["text"] for s in m2["surahs"] for x in s["ayahs"]}
    held: set[str] = set()
    for case in json.loads((ROOT / "eval" / "uthmani_heldout.json").read_text(encoding="utf-8"))["cases"]:
        for g in case["gold"]:
            held.update(f"{g['surah']}:{a}" for a in range(g["ayah_start"], g["ayah_end"] + 1))

    changed = collections.Counter()
    for k, text in imlai.items():
        for w in words_of(text):
            if uthmani.search_fold(w) != arabic.folded(w):
                changed[w] += 1

    report: dict = {"when": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "excluded_heldout_verses": sorted(held) if args.exclude_heldout else None,
                    "imlai_words_changed_by_the_uthmani_fold": sum(changed.values()), "texts": {}}
    for name, text in (("tanzil", tanzil), ("mushaf2", mushaf2)):
        verses = ok = length_mismatch = differing = explained = vowel_conflicts = 0
        residual: collections.Counter = collections.Counter()
        for k, imla in imlai.items():
            if args.exclude_heldout and k in held or args.only_heldout and k not in held:
                continue
            verses += 1
            u = [p for w in words_of(text[k]) for p in parts(w)]
            i = words_of(imla)
            if len(u) != len(i):
                length_mismatch += 1
                residual[("word boundaries differ", " ".join(u[:3]) + " …")] += 1
                continue
            good = True
            for qw, sw in zip(u, i):
                if arabic.literal(qw) == arabic.literal(sw):
                    continue
                differing += 1
                if uthmani.explain(qw, sw) is not None:
                    explained += 1
                    vowel_conflicts += bool(uthmani.vowel_conflicts(qw, sw))
                elif not uthmani.features(qw) and arabic.letters(qw).replace("ٱ", "ا").replace("ى", "ي") == arabic.letters(sw).replace("ى", "ي"):
                    explained += 1  # same letters, only marks differ: the ordinary rules judge these
                else:
                    good = False
                    residual[(qw, sw)] += 1
            ok += good
        report["texts"][name] = {
            "verses": verses, "verses_fully_explained": ok, "share": round(ok / verses, 4), "word_boundary_mismatch_verses": length_mismatch,
            "words_differing_from_the_imlai_literal": differing, "words_explained": explained, "vowel_conflicts_among_explained": vowel_conflicts,
            "unexplained_words_distinct": len(residual), "top_unexplained": [[a, b, c] for (a, b), c in residual.most_common(40)],
        }
    out = ROOT / "eval" / "results" / f"uthmani-rules-{time.strftime('%Y%m%d-%H%M%S')}{'-excl-heldout' if args.exclude_heldout else '-heldout-verses' if args.only_heldout else ''}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, r in report["texts"].items():
        print(f"{name}: {r['verses_fully_explained']}/{r['verses']} verses fully explained ({100 * r['share']:.1f}%); "
              f"{r['words_explained']}/{r['words_differing_from_the_imlai_literal']} differing words explained; "
              f"{r['word_boundary_mismatch_verses']} verses with different word boundaries; vowel conflicts {r['vowel_conflicts_among_explained']}")
    print(f"imla'i words changed by the Uthmani fold: {report['imlai_words_changed_by_the_uthmani_fold']}")
    print(f"saved {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
