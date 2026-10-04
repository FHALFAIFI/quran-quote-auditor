"""No article text in any log line: the scrubber (app/logging_safety.py), the app's own log calls, and a real uvicorn process
whose access and error logs are captured while it serves an audit, a validation error, a 413 and an unhandled exception."""

import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import logging_safety
from app.logging_safety import MAX_ARABIC_LETTERS, scrub

ROOT = Path(__file__).resolve().parent.parent
SENTINEL = "هذه جملة اختبارية فريدة لا ينبغي أن تظهر في أي سجل من سجلات الخادم أبدا"
MARK = "اختبارية"  # a word that appears only in the sentinel
ARTICLE = f"{SENTINEL}. قال تعالى: ﴿اقرأ باسم ربك الذي خلق﴾ (العلق: 1)."


# --- the scrubber ------------------------------------------------------------------------------------------------------

def test_scrub_removes_long_arabic_runs_only():
    assert MARK not in scrub(f"error: {SENTINEL}")
    assert "[Arabic text removed:" in scrub(SENTINEL)
    assert scrub("POST /api/audit HTTP/1.1 200") == "POST /api/audit HTTP/1.1 200"
    short = "سورة البقرة"  # under the threshold: kept
    assert scrub(f"surah {short}") == f"surah {short}"
    assert scrub("ا" * MAX_ARABIC_LETTERS) == "ا" * MAX_ARABIC_LETTERS
    assert scrub("ا" * (MAX_ARABIC_LETTERS + 1)) != "ا" * (MAX_ARABIC_LETTERS + 1)


def test_scrub_decodes_percent_encoded_arabic():
    path = "/api/audit?q=" + httpx.QueryParams({"x": SENTINEL}).get("x").encode().hex()  # not Arabic: kept
    assert scrub(path) == path
    from urllib.parse import quote

    encoded = "/?q=" + quote(SENTINEL)
    assert "%D8" in encoded
    out = scrub(encoded)
    assert MARK not in out and "%D8" not in out and "[Arabic text removed:" in out


def test_record_scrubbed_keeps_uvicorn_access_shape():
    from uvicorn.logging import AccessFormatter
    from urllib.parse import quote

    record = logging.getLogger("uvicorn.access").makeRecord(
        "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", "/?q=" + quote(SENTINEL), "1.1", 200), None)
    line = AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False).format(record)
    assert MARK not in line and "%D8" not in line and line.startswith("127.0.0.1:5000")


def test_traceback_with_article_text_is_redacted(caplog):
    logging_safety.install()
    caplog.set_level(logging.ERROR)
    try:
        raise ValueError(f"bad input: {SENTINEL}")
    except ValueError:
        logging.getLogger("uvicorn.error").exception("Exception in ASGI application")
    text = caplog.text
    assert "Exception in ASGI application" in text
    assert MARK not in text and "[Arabic text removed:" in text


def test_args_and_objects_are_redacted(caplog):
    caplog.set_level(logging.INFO)
    log = logging.getLogger("some.module")
    log.info("article %s", SENTINEL)
    log.info("dict %(a)s", {"a": SENTINEL})
    log.warning("object %s", ValueError(SENTINEL))
    log.info(SENTINEL)
    assert MARK not in caplog.text
    assert caplog.text.count("[Arabic text removed:") == 4


# --- the app, in process ------------------------------------------------------------------------------------------------

@pytest.fixture
def client(use_source):
    main._hits.clear()
    yield TestClient(main.app, raise_server_exceptions=False)
    main._hits.clear()


def test_app_logs_no_article_text(client, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    assert client.post("/api/audit", json={"article": ARTICLE}).status_code == 200
    assert client.post("/api/audit", json={"article": ARTICLE, "extra": SENTINEL}).status_code == 422
    assert client.post("/api/audit", json={"article": ARTICLE * 400}).status_code == 413
    assert client.post("/api/phrase", json={"article": ARTICLE, "start": 0, "end": 5}).status_code in (200, 400)
    assert client.post("/api/suggest", json={"before": SENTINEL + " قال تعالى"}).status_code == 200

    def boom(article):
        raise ValueError(f"cannot audit: {article}")

    monkeypatch.setattr(main, "run_audit", boom)
    assert client.post("/api/audit", json={"article": ARTICLE}).status_code == 500
    assert "unhandled error on /api/audit: ValueError" in caplog.text
    assert MARK not in caplog.text


# --- a real uvicorn process ---------------------------------------------------------------------------------------------

SERVER = r"""
import json, sys, time
sys.path.insert(0, {root!r})
import uvicorn
import app.main as main
import app.audit as audit
from app.quran_source import build_index
records = json.load(open({fixture!r}, encoding="utf-8"))["ayahs"]
index = build_index(records, time.time())
class Fake:
    def get(self): return index
    def status(self): return {{"loaded": True, "stale": False}}
audit.source = Fake(); main.source = Fake(); audit.get_provider = lambda: None; main.get_provider = lambda: None
real = main.run_audit
def run_audit(article):
    if article.startswith("BOOM"):
        raise ValueError("cannot audit: " + article)
    return real(article)
main.run_audit = run_audit
uvicorn.run(main.app, host="127.0.0.1", port={port}, log_level="info")
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_uvicorn_access_and_error_logs_have_no_article_text(tmp_path):
    port = _free_port()
    script = tmp_path / "server.py"
    script.write_text(SERVER.format(root=str(ROOT), fixture=str(ROOT / "tests/fixtures/hafs_subset.json"), port=port))
    logfile = tmp_path / "server.log"
    env = {**os.environ, "AI_PROVIDER": "none", "GROQ_API_KEY": "", "GEMINI_API_KEY": "", "PYTHONUNBUFFERED": "1"}
    with open(logfile, "wb") as out:
        proc = subprocess.Popen([sys.executable, str(script)], stdout=out, stderr=subprocess.STDOUT, env=env)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(100):
                try:
                    httpx.get(base + "/api/health", timeout=1)
                    break
                except httpx.HTTPError:
                    time.sleep(0.1)
            with httpx.Client(base_url=base, timeout=10) as c:
                assert c.post("/api/audit", json={"article": ARTICLE}).status_code == 200
                assert c.post("/api/audit", json={"article": ARTICLE, "extra": SENTINEL}).status_code == 422
                assert c.post("/api/audit", content=ARTICLE.encode() * 800,
                              headers={"content-type": "application/json"}).status_code == 413

                def chunked():
                    yield b'{"article": "'
                    for _ in range(800):
                        yield ARTICLE.encode()
                    yield b'"}'

                assert c.post("/api/audit", content=chunked(), headers={"content-type": "application/json"}).status_code == 413
                assert c.get("/", params={"q": SENTINEL}).status_code == 200  # article text in a query string
                # last: uvicorn closes the connection after an exception escapes the app
                assert c.post("/api/audit", json={"article": "BOOM " + ARTICLE}).status_code == 500
        finally:
            proc.terminate()
            proc.wait(timeout=10)
    log = logfile.read_text(encoding="utf-8", errors="replace")
    assert '"POST /api/audit HTTP/1.1" 200' in log
    assert '"POST /api/audit HTTP/1.1" 413' in log
    assert "unhandled error on /api/audit: ValueError" in log
    # Since the provider-harness release (d65befa) an unexpected error is answered inside the app, so uvicorn writes no traceback
    # at all; the scrubber remains the second guard for any other record.
    assert "Exception in ASGI application" not in log and "Traceback" not in log
    assert MARK not in log
    assert "%D8%A7%D8%AE%D8%AA%D8%A8%D8%A7%D8%B1%D9%8A%D8%A9" not in log.upper()  # the mark, percent-encoded
