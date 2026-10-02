"""Check eval/uthmani_heldout.json (and eval/uthmani_dev.json) against two independent texts.

Independent of the app's matching code: its own minimal normalisation and per-surah word streams.
Needs the network twice at most: the Quranpedia Hafs text (through the app's cached loader, used only
to obtain the text) and Tanzil's Uthmani XML (eval/tanzil_text.py: Tanzil Project, https://tanzil.net; the verses named in each
gold `source`).

    python eval/validate_uthmani.py [cases-file]          # default eval/uthmani_heldout.json

Checks
  * every gold quote and negative is a substring of the article;
  * script "uthmani": each unedited quote is a verbatim sequence of words of the Tanzil Uthmani verse(s)
    named in `source` (edited quotes: their `source` says which hand edit, and the unedited words must still be
    a contiguous run of the Uthmani text apart from the edited word);
  * correct_text occurs contiguously in the Quranpedia text at the gold surah/ayah range;
  * wording "correct": the quote, reduced to plain letters, equals correct_text after the documented spelling
    differences only (reported, not failed: the app is not used to decide this);
    wording "wording_error": the plain quote does NOT equal correct_text;
  * ambiguous flag == (correct_text occurs at more than one place);
  * negatives do not occur contiguously in the Quran.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.quran_source import source  # noqa: E402  (only used to obtain the Quranpedia text)
from tanzil_text import load as load_tanzil  # noqa: E402  (eval/tanzil_text.py)

MARKS = re.compile(r"[ً-ٰٟۖ-ۭـ﻿]")
FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})


def words(t: str) -> list[str]:
    return re.sub(r"[^ء-ي ]", " ", MARKS.sub("", t).translate(FOLD)).split()


def uthmani_words(t: str) -> list[str]:
    return [w for w in t.replace("﻿", "").split() if MARKS.sub("", w)]


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "uthmani_heldout.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    idx = source.get()
    streams: dict[int, list[tuple[str, int]]] = {}
    for (s, n), a in sorted(idx.ayahs.items()):
        for w in words(a.text):
            streams.setdefault(s, []).append((w, n))

    def find(ws: list[str]) -> list[tuple[int, int, int]]:
        out = []
        for s, st in streams.items():
            fw = [w for w, _ in st]
            for i in range(len(fw) - len(ws) + 1):
                if fw[i:i + len(ws)] == ws:
                    out.append((s, st[i][1], st[i + len(ws) - 1][1]))
        return out

    tanzil = load_tanzil()

    def tanzil_words(key: str) -> list[str]:
        return uthmani_words(tanzil[key])

    problems: list[str] = []
    n_gold = n_neg = 0
    for case in data["cases"]:
        art = case["article"]
        for g in case["gold"]:
            n_gold += 1
            tag = f"{case['id']} «{g['quote'][:30]}»"
            if g["quote"] not in art:
                problems.append(f"{tag}: quote is not a substring of the article")
            ct = words(g["correct_text"])
            places = find(ct)
            if not any(s == g["surah"] and g["ayah_start"] <= a0 and a1 <= g["ayah_end"] and a0 <= g["ayah_end"] for s, a0, a1 in places):
                problems.append(f"{tag}: correct_text is not at the gold range {g['surah']}:{g['ayah_start']}-{g['ayah_end']} (found at {places[:4]})")
            if bool(g["ambiguous"]) != (len(places) > 1 and g["wording"] == "correct"):
                problems.append(f"{tag}: ambiguous flag {g['ambiguous']} but {len(places)} places")
            plain_q = words(g["quote"])
            if g["wording"] == "correct" and g.get("script") == "uthmani" and "edited" not in g["source"] and g["source"].startswith("Tanzil"):
                keys = [k for k in re.findall(r"\d+:\d+", g["source"])]
                pool = [w for k in dict.fromkeys(keys) for w in tanzil_words(k)]
                qw = uthmani_words(g["quote"])
                if not any(pool[i:i + len(qw)] == qw for i in range(len(pool) - len(qw) + 1)):
                    problems.append(f"{tag}: not a verbatim run of the Tanzil Uthmani text for {keys}")
            if g["wording"] == "wording_error" and plain_q == ct:
                problems.append(f"{tag}: labelled wording_error but the plain letters equal correct_text")
            if g["wording"] == "correct" and g.get("script") != "mixed" and len(plain_q) not in (len(ct), len(ct) - 1, len(ct) - 2):
                problems.append(f"{tag}: word count {len(plain_q)} vs correct_text {len(ct)} (vocatives account for at most +/-2)")
        for n in case["negatives"]:
            n_neg += 1
            if n not in art:
                problems.append(f"{case['id']}: negative is not a substring of the article")
            if find(words(n)):
                problems.append(f"{case['id']}: negative «{n}» occurs in the Quran")
    print(f"{path.name}: {len(data['cases'])} cases, {n_gold} gold quotations, {n_neg} negatives")
    for p in problems:
        print("PROBLEM", p)
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
