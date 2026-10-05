"""Write app/data/prose_zipf.tsv: for every folded word of the Quran text, its frequency in ordinary Arabic.

    pip install wordfreq==3.1.1        # not a dependency of the app; only this builder needs it
    .venv/bin/python eval/build_prose_zipf.py

Frequency = wordfreq's Zipf value for Arabic (log10 of occurrences per billion words; 3 = once per million), the highest over the
plain spellings in the Quran text that fold to the word (and their bare-alef forms). Data: wordfreq by Robyn Speer, CC BY-SA 4.0
(https://github.com/rspeer/wordfreq); the written file carries the same licence. Used by app/phrases.find_pairs.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import wordfreq  # noqa: E402

from app import arabic  # noqa: E402
from app.quran_source import source  # noqa: E402

idx = source.get()
spell: dict[str, set[str]] = {}
for a in idx.ayahs.values():
    for w, f in zip(a.words, a.folded):
        spell.setdefault(f, set()).add(arabic.letters(w))
rows = []
for f in sorted(spell):
    z = max(wordfreq.zipf_frequency(v, "ar") for s in spell[f] for v in {s, re.sub("[أإآٱ]", "ا", s), f})
    rows.append(f"{f}\t{z:.2f}")
out = ROOT / "app" / "data" / "prose_zipf.tsv"
out.write_text(
    "# Folded Quran word -> frequency in ordinary Arabic (Zipf; wordfreq 3.1.1, language \"ar\"). Built by eval/build_prose_zipf.py.\n"
    "# Derived from wordfreq data by Robyn Speer, https://github.com/rspeer/wordfreq, licensed CC BY-SA 4.0; this file is CC BY-SA 4.0.\n"
    + "\n".join(rows) + "\n", encoding="utf-8")
print(len(rows), "words written to", out)
