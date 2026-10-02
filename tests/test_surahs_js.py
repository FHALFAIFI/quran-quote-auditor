"""The browser's surah list (app/static/surahs.js) must equal app/surahs.py: a wrong number would pin a quotation to the wrong verse."""

import json
import re
from pathlib import Path

from app.surahs import SURAHS


def test_surahs_js_matches_python_table():
    text = (Path(__file__).resolve().parent.parent / "app" / "static" / "surahs.js").read_text(encoding="utf-8")
    payload = re.search(r"window\.SURAHS = (\[.*\]);", text, re.S).group(1)
    assert [tuple(x) for x in json.loads(payload)] == SURAHS
