"""Write the 36-verse test excerpt as the app's Quran cache, so a server started in CI never asks Quranpedia for the text.

    QURAN_CACHE_DIR=/tmp/qqa-cache python scripts/ci_fixture_cache.py

The app reads ``$QURAN_CACHE_DIR/hafs-mushaf-1.json`` before it would fetch anything; the file written here is marked fresh, so for the
next 24 hours the server answers from these 36 verses only (``/api/health`` then shows ``source.ayahs: 36``, ``loaded_from: "disk"``).
Used only by the CI workflow and by browser suites written for the excerpt (``scripts/ui_pilot_journey_e2e.mjs``); the deployed app
always loads the whole, current text. The excerpt and its credit: ``tests/fixtures/hafs_subset.json`` and ``SOURCES.md`` §1.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "hafs_subset.json"


def main() -> int:
    cache_dir = os.environ.get("QURAN_CACHE_DIR")
    if not cache_dir:
        print("set QURAN_CACHE_DIR to the directory the server will read", file=sys.stderr)
        return 2
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    out = Path(cache_dir) / "hafs-mushaf-1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"fetched_at": time.time(), "source": f"test excerpt: {FIXTURE.relative_to(ROOT)}", "ayahs": data["ayahs"]},
                              ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(data['ayahs'])} verses to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
