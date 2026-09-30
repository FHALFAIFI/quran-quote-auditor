"""Check eval/phrases_frozen.json against the Quranpedia Hafs text.

Independent of the app's matching code: its own minimal normalization, its own per-surah word
streams (so a phrase that crosses a verse boundary is found), and it only reads the source text.

    python eval/validate_phrases.py [cases-file]     # default eval/phrases_frozen.json

Checks
  * gold  "correct": the quote equals the Hafs wording and occurs contiguously in the Quran;
  * gold  "wording_error": the quote does NOT occur contiguously (it really is a misquotation),
    differs from correct_text by only a few words, and correct_text does occur;
  * ambiguous flag == (correct_text occurs at more than one place);
  * the gold surah/ayah is one of the places where correct_text occurs;
  * negatives never occur contiguously in the Quran; formulas always do;
  * quotes/negatives/formulas are substrings of the article, and gold spans do not overlap.
Report (information, not failures): every run of >= 3 article words that occurs in the Quran OUTSIDE
the gold quotations ("incidental runs"). Negatives containing such a run are the 'hard' negatives.
"""

from __future__ import annotations

import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.quran_source import source  # noqa: E402  (only used to obtain the source text)

MARKS = re.compile(r"[ً-ٰٟۖ-ۭـ﻿]")
FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})


def words(t: str) -> list[str]:
    return re.sub(r"[^ء-ي ]", " ", MARKS.sub("", t)).translate(FOLD).split()


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "phrases_frozen.json"
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

    problems: list[str] = []
    n_gold = n_neg = n_form = 0
    incidental: list[tuple[str, str, int, bool]] = []
    hard_negatives = 0
    for case in data["cases"]:
        art = case["article"]
        spans = []
        for g in case["gold"]:
            n_gold += 1
            tag = f"{case['id']} «{g['quote']}»"
            if g["quote"] not in art:
                problems.append(f"{tag}: quote not in article")
                continue
            p = art.index(g["quote"])
            spans.append((p, p + len(g["quote"])))
            cw, qw = words(g["correct_text"]), words(g["quote"])
            locs = find(cw)
            if not locs:
                problems.append(f"{tag}: correct_text does not occur in the Quran")
            if g["ambiguous"] != (len(locs) > 1):
                problems.append(f"{tag}: ambiguous={g['ambiguous']} but correct_text occurs at {len(locs)} place(s)")
            if (g["surah"], g["ayah_start"], g["ayah_end"]) not in locs:
                problems.append(f"{tag}: gold location {g['surah']}:{g['ayah_start']}-{g['ayah_end']} is not where correct_text occurs ({locs[:3]})")
            if g["reference"] != "missing" or g["reference_text"]:
                problems.append(f"{tag}: frozen-set quotations must have no written reference")
            if g["wording"] == "correct":
                if qw != cw:
                    problems.append(f"{tag}: labelled correct but differs from correct_text")
            elif g["wording"] == "wording_error":
                if find(qw):
                    problems.append(f"{tag}: labelled wording_error but the quote occurs in the Quran as written")
                ops = [o for o in SequenceMatcher(None, qw, cw, autojunk=False).get_opcodes() if o[0] != "equal"]
                if len(ops) > 3 or sum(max(o[2] - o[1], o[4] - o[3]) for o in ops) > 4:
                    problems.append(f"{tag}: not a slight misquotation ({len(ops)} edit blocks)")
            else:
                problems.append(f"{tag}: unsupported wording label {g['wording']}")
        spans.sort()
        for a, b in zip(spans, spans[1:]):
            if b[0] < a[1]:
                problems.append(f"{case['id']}: gold quotations overlap")
        for neg in case["negatives"]:
            n_neg += 1
            if neg not in art:
                problems.append(f"{case['id']}: negative «{neg}» not in article")
            if find(words(neg)):
                problems.append(f"{case['id']}: negative «{neg}» occurs in the Quran")
        for f in case.get("formulas", []):
            n_form += 1
            if f not in art:
                problems.append(f"{case['id']}: formula «{f}» not in article")
            if not find(words(f)):
                problems.append(f"{case['id']}: formula «{f}» does not occur in the Quran (it should)")
        # incidental runs: maximal >= 3-word runs of the article that occur in the Quran, outside gold spans
        toks = [(m.start(), m.end(), w) for m in re.finditer(r"[ء-ْٰـ]+", art) for w in [words(m.group(0))] if w]
        toks = [(s, e, w[0]) for s, e, w in toks]
        i = 0
        while i < len(toks):
            j = i + 1
            best = 0
            # words are contiguous only when separated by whitespace alone (punctuation, digits or quotes break a run)
            while j <= len(toks) and (j == i + 1 or not art[toks[j - 2][1]:toks[j - 1][0]].strip()) and find([t[2] for t in toks[i:j]]):
                best = j
                j += 1
            if best - i >= 3:
                s0, e0 = toks[i][0], toks[best - 1][1]
                inside_gold = any(a <= s0 and e0 <= b for a, b in spans)
                if not inside_gold:
                    incidental.append((case["id"], art[s0:e0], best - i, any(art[s0:e0] in n for n in case["negatives"])))
                i = best
            else:
                i += 1
    hard = sorted({(c, r) for c, r, _, inside in incidental if inside})
    print(f"cases={len(data['cases'])} gold={n_gold} negatives={n_neg} formulas={n_form}")
    print(f"incidental >=3-word Quran runs outside gold quotations: {len(incidental)} (inside negatives = 'hard' negatives: {len(hard)})")
    for c, run, n, inside in incidental:
        print(f"  {'HARD-NEG' if inside else 'in-prose'} {c}: «{run}» ({n} words)")
    for p in problems:
        print("PROBLEM:", p)
    print("labels OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
