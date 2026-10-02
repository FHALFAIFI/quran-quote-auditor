"""The Tanzil Quran text (Uthmani, Version 1.1) for the evaluation scripts.

Source: Tanzil Project, https://tanzil.net (Creative Commons Attribution 3.0). Terms (from the file's own notice): verbatim
copies may be copied and distributed, changing the text is not allowed, the source (Tanzil Project) must be clearly indicated
with a link to tanzil.net, and the copyright notice is reproduced in every file that contains a substantial portion of the
text. The notice is kept inside each data file of this repository that quotes the text. Running this module downloads Tanzil's
XML once from tanzil.net (options: pause marks, sajdah signs, rub-el-hizb signs, superscript alefs, tatweel); by running it you
accept the terms on https://tanzil.net/download/. Nothing is committed.

    from tanzil_text import load
    verses = load()                  # {"2:43": "...", ...}, 6,236 verses, the `text` attribute of each <aya>

Order: the path in the environment variable TANZIL_XML (a file you already downloaded), else the cached download in the system
temp directory, else a fresh download.
"""

from __future__ import annotations

import os
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

URL = ("https://tanzil.net/pub/download/index.php?quranType=uthmani&outType=xml"
       "&marks=true&sajdah=true&rub=true&alef=true&tatweel=true")
UA = {"User-Agent": "quran-quote-auditor-eval/0.1 (one request)"}
CACHE = Path(tempfile.gettempdir()) / "quran-uthmani-check" / "tanzil-uthmani.xml"


def xml_path() -> Path:
    env = os.environ.get("TANZIL_XML")
    if env:
        return Path(env)
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_bytes(urllib.request.urlopen(urllib.request.Request(URL, headers=UA), timeout=120).read())
    return CACHE


def load() -> dict[str, str]:
    raw = xml_path().read_bytes()
    if b"Tanzil Quran Text (Uthmani, Version 1.1)" not in raw:
        raise SystemExit("not the Tanzil Uthmani v1.1 XML (its copyright block is missing): " + str(xml_path()))
    root = ET.fromstring(raw)
    out = {f"{s.get('index')}:{a.get('index')}": a.get("text") for s in root.iter("sura") for a in s.iter("aya")}
    if len(out) != 6236:
        raise SystemExit(f"expected 6,236 verses in the Tanzil XML, found {len(out)}")
    return out
