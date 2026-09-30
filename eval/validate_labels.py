"""Check the hand-written gold labels against the Quranpedia Hafs text.

Independent of the app's verifier: it uses its own minimal normalization and
only reads the source text (fetched live from Quranpedia, cached per machine).

    python eval/validate_labels.py [cases-file]     # default eval/cases.json
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.quran_source import source  # noqa: E402  (only used to obtain the source text)
from app.surahs import ALIASES, AYAH_COUNTS, NAMES  # noqa: E402  (metadata)

MARKS = re.compile(r"[ً-ٰٟۖ-ۭـ﻿]")
FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})


def plain(t: str) -> str:  # letters only, exact letter forms
    return " ".join(re.sub(r"[^ء-ي ]", " ", MARKS.sub("", t)).split())


def fold(t: str) -> str:
    return plain(t).translate(FOLD)


def vocal(t: str) -> str:  # letters + harakat, annotation marks removed, canonical mark order
    t = unicodedata.normalize("NFC", t)
    t = re.sub(r"[ۖ-ۭـ﻿]", "", t)
    return " ".join(t.split())


def within(needle: str, hay: str) -> bool:
    return f" {needle} " in f" {hay} "


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "cases.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    idx = source.get()
    by_surah: dict[int, list] = {}
    for (s, n), a in idx.ayahs.items():
        by_surah.setdefault(s, []).append((n, a.text))
    all_folded = {(s, n): fold(a.text) for (s, n), a in idx.ayahs.items()}
    name_to_num = {fold(v): k for k, v in NAMES.items()} | {fold(a): k for k, al in ALIASES.items() for a in al}
    problems, n_gold = [], 0

    for case in data["cases"]:
        art = case["article"]
        for g in case["gold"]:
            n_gold += 1
            tag = f"{case['id']} «{g['quote']}»"
            if g["quote"] not in art:
                problems.append(f"{tag}: quote not in article")
            if g["reference_text"] and g["reference_text"] not in art:
                problems.append(f"{tag}: reference_text not in article")
            span = " ".join(a.text for a in (idx.ayahs[(g["surah"], k)] for k in range(g["ayah_start"], g["ayah_end"] + 1)))
            if not within(fold(g["correct_text"]), fold(span)):
                problems.append(f"{tag}: correct_text not found in {g['surah']}:{g['ayah_start']}-{g['ayah_end']}")
            if g["wording"] == "correct" and fold(g["quote"]) != fold(g["correct_text"]):
                problems.append(f"{tag}: labelled correct but differs from correct_text")
            if g["wording"] == "wording_error" and fold(g["quote"]) == fold(g["correct_text"]):
                problems.append(f"{tag}: labelled wording_error but letters match")
            if g["wording"] == "diacritics_error":
                if plain(g["quote"]) != plain(g["correct_text"]):
                    problems.append(f"{tag}: diacritics_error but letters differ")
                if vocal(g["correct_text"]) not in vocal(span):
                    problems.append(f"{tag}: vocalized correct_text not found verbatim in source (check diacritics)")
            occ = sum(within(fold(g["correct_text"]), t) for t in all_folded.values())
            if g["ambiguous"] != (occ > 1):
                problems.append(f"{tag}: ambiguous={g['ambiguous']} but phrase occurs in {occ} verse(s)")
            # reference label vs the written reference
            if g["reference_text"] and g["reference_text"].startswith("سورة ") and ":" not in g["reference_text"]:
                surah = name_to_num.get(fold(g["reference_text"][5:]))
                expected = "surah_only" if surah == g["surah"] else "incorrect"
                if expected != g["reference"]:
                    problems.append(f"{tag}: reference labelled {g['reference']} but written surah-only reference implies {expected}")
            elif g["reference_text"]:
                m = re.match(r"(.+?)\s*[:：]\s*(\d+)(?:\s*-\s*(\d+))?$", g["reference_text"])
                surah = name_to_num.get(fold(m.group(1))) if m else None
                a1 = int(m.group(2)) if m else None
                a2 = int(m.group(3)) if m and m.group(3) else a1
                if surah is None:
                    problems.append(f"{tag}: cannot read reference_text")
                else:
                    out_of_range = a1 > AYAH_COUNTS[surah] or a2 > AYAH_COUNTS[surah]
                    exact = surah == g["surah"] and a1 == g["ayah_start"] and a2 == g["ayah_end"]
                    overlaps = surah == g["surah"] and a1 <= g["ayah_end"] and g["ayah_start"] <= a2
                    expected = "out_of_range" if out_of_range else "correct" if exact else "partial" if overlaps else "incorrect"
                    if g["ambiguous"] and not exact:
                        # for repeated phrases a reference is correct if it points to ANY occurrence
                        ref_hit = within(fold(g["correct_text"]), " ".join(all_folded.get((surah, k), "") for k in range(a1, a2 + 1)))
                        expected = "out_of_range" if out_of_range else "correct" if ref_hit else "incorrect"
                    if expected != g["reference"]:
                        problems.append(f"{tag}: reference labelled {g['reference']} but written reference implies {expected}")
            elif g["reference"] != "missing":
                problems.append(f"{tag}: no reference_text but label is {g['reference']}")
        for neg in case["negatives"]:
            if neg not in art:
                problems.append(f"{case['id']}: negative «{neg}» not in article")
            hits = [k for k, t in all_folded.items() if within(fold(neg), t)]
            if hits:
                problems.append(f"{case['id']}: negative «{neg}» occurs in the Quran at {hits[:3]}")

    print(f"cases={len(data['cases'])} gold quotations={n_gold} negatives={sum(len(c['negatives']) for c in data['cases'])}")
    for p in problems:
        print("PROBLEM:", p)
    print("labels OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
