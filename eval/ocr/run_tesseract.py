"""Run Tesseract (self-hosted, `ara`) over the benchmark pages and write a run record for score_ocr.py.

    python eval/ocr/run_tesseract.py --manifest M.json --pages-dir DIR --out RUN.json [--psm N] [--oem N]

Runs `tesseract <image> - -l ara` once per page, locally. It does not install anything: if `tesseract` is not on
PATH, or its `ara` language data is missing, it exits with a message and writes nothing. No cloud engine is called by
this script or anywhere in eval/ocr/. The page images live outside the repository (``--pages-dir``) unless a page's
rights record allows them in.

Cost: self-hosted, so no per-page charge is recorded; machine time is recorded per page, and the host description is
written into the run record so times are not compared across machines by mistake.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PAGE_TIMEOUT_S = 300


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--pages-dir", required=True, type=Path, help="folder that image_path is relative to (outside git)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--lang", default="ara")
    ap.add_argument("--psm", type=int, default=None, help="tesseract --psm (page segmentation mode); default: tesseract's")
    ap.add_argument("--oem", type=int, default=None, help="tesseract --oem (engine mode); default: tesseract's")
    a = ap.parse_args(argv)

    exe = shutil.which("tesseract")
    if not exe:
        print("tesseract is not installed (not on PATH). This script does not install system packages; "
              "install Tesseract and its 'ara' data yourself, then run it again. Nothing was written.", file=sys.stderr)
        return 3
    langs = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=60)
    if a.lang not in (langs.stdout + langs.stderr).split():
        print(f"tesseract has no '{a.lang}' language data (tesseract --list-langs). Nothing was written.", file=sys.stderr)
        return 3
    version = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
    version_line = ((version.stdout or version.stderr).splitlines() or ["unknown"])[0]

    manifest = json.loads(a.manifest.read_text(encoding="utf-8"))
    extra = []
    if a.psm is not None:
        extra += ["--psm", str(a.psm)]
    if a.oem is not None:
        extra += ["--oem", str(a.oem)]

    pages = []
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for p in manifest.get("pages", []):
        rec = {"page_id": p["page_id"], "text": None, "seconds": None, "cost": None, "error": None}
        img = p.get("image_path")
        path = a.pages_dir / img if isinstance(img, str) else None
        if path is None or not path.is_file():
            rec["error"] = "image not found"
        else:
            t0 = time.perf_counter()
            try:
                res = subprocess.run([exe, str(path), "-", "-l", a.lang, *extra], capture_output=True, timeout=PAGE_TIMEOUT_S)
                rec["seconds"] = round(time.perf_counter() - t0, 3)
                if res.returncode != 0:
                    rec["error"] = f"tesseract exit {res.returncode}"
                else:
                    rec["text"] = res.stdout.decode("utf-8", errors="replace")
            except subprocess.TimeoutExpired:
                rec["seconds"] = round(time.perf_counter() - t0, 3)
                rec["error"] = f"timeout after {PAGE_TIMEOUT_S} s"
        pages.append(rec)
        print(f"{rec['page_id']}: {'ok' if rec['error'] is None else rec['error']} ({rec['seconds']} s)", file=sys.stderr)

    run = {
        "engine": {"name": "tesseract", "version": version_line, "lang": a.lang, "args": extra, "deployment": "self-hosted"},
        "started_at": started,
        "host": {"platform": platform.platform(), "machine": platform.machine(), "cpus": os.cpu_count()},
        "cost_note": "self-hosted: no per-page charge recorded; hosting cost is not attributed per page",
        "manifest": str(a.manifest),
        "pages": pages,
    }
    a.out.write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {a.out} ({sum(r['error'] is None for r in pages)}/{len(pages)} pages read)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
