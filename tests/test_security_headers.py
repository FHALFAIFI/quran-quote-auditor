"""Security headers on every kind of response, the request-body cap (also for chunked bodies), malformed-JSON abuse,
and the self-hosted fonts (no third-party request from any page)."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.main import CSP, MAX_BODY_BYTES, SECURITY_HEADERS, app
from app.suggest import MAX_AFTER, MAX_BEFORE

STATIC = Path(main.__file__).parent / "static"
PAGES = ["/", "/sources", "/privacy", "/limitations", "/roadmap"]
HTML_FILES = ["index.html", "sources.html", "privacy.html", "limitations.html", "roadmap.html"]
FONT_DIRS = ["amiri-quran", "noto-naskh-arabic", "readex-pro"]

EXPECTED_CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; "
                "connect-src 'self'; worker-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
                "form-action 'self'")


@pytest.fixture
def client(use_source):
    main._hits.clear()  # the per-IP limiter is shared by every test in the process
    yield TestClient(app, raise_server_exceptions=False)
    main._hits.clear()


def assert_security_headers(res, api=False):
    for k, v in SECURITY_HEADERS.items():
        assert res.headers.get(k) == v, (k, res.headers.get(k))
    assert "strict-transport-security" not in res.headers  # plain http in the test client
    if api:
        assert res.headers["cache-control"] == "no-store"


def test_csp_string_is_strict():
    assert CSP == EXPECTED_CSP
    assert "unsafe-inline" not in CSP and "unsafe-eval" not in CSP
    assert "googleapis" not in CSP and "gstatic" not in CSP and "https:" not in CSP


@pytest.mark.parametrize("path", PAGES + ["/static/styles.css", "/static/app.js",
                                          "/static/fonts/readex-pro/readex-pro-arabic.woff2",
                                          "/static/fonts/amiri-quran/OFL.txt"])
def test_headers_on_pages_and_static_files(client, path):
    res = client.get(path)
    assert res.status_code == 200
    assert_security_headers(res)
    assert "cache-control" not in res.headers or res.headers["cache-control"] != "no-store"


def test_headers_on_api_and_error_responses(client):
    assert_security_headers(client.get("/api/health"), api=True)
    assert_security_headers(client.get("/no-such-page"))  # 404
    res = client.post("/api/audit", json={"text": "x"})  # 422
    assert res.status_code == 422
    assert_security_headers(res, api=True)
    res = client.post("/api/audit", content=b"x" * (MAX_BODY_BYTES + 1), headers={"content-type": "application/json"})
    assert res.status_code == 413
    assert_security_headers(res, api=True)


def test_headers_on_unhandled_500(client, monkeypatch):
    def boom(article):
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "run_audit", boom)
    res = client.post("/api/audit", json={"article": "نص"})
    assert res.status_code == 500
    assert_security_headers(res, api=True)
    assert res.json() == {"error": "حدث خطأ غير متوقع أثناء التدقيق."}


def test_hsts_only_over_https(client):
    assert "strict-transport-security" not in client.get("/").headers
    res = client.get("/", headers={"x-forwarded-proto": "https"})
    assert res.headers["strict-transport-security"] == "max-age=31536000"
    assert "strict-transport-security" not in client.get("/", headers={"x-forwarded-proto": "http"}).headers
    https = TestClient(app, base_url="https://testserver")
    assert https.get("/sources").headers["strict-transport-security"] == "max-age=31536000"


# --- the body cap ------------------------------------------------------------------------------------------------------

def _chunks(total: int, size: int = 8192):
    sent = 0
    while sent < total:
        n = min(size, total - sent)
        sent += n
        yield b" " * n  # JSON whitespace: valid padding if it were ever parsed


def test_content_length_over_cap_is_413(client):
    res = client.post("/api/audit", content=b"{" + b" " * MAX_BODY_BYTES + b"}", headers={"content-type": "application/json"})
    assert res.status_code == 413
    assert res.json() == {"error": "حجم الطلب أكبر من المسموح."}


def test_chunked_body_without_content_length_is_capped(client):
    """A generator body is sent with Transfer-Encoding: chunked and no Content-Length: the old check let it through."""
    seen = {}

    def body():
        yield b'{"article": "'
        yield from _chunks(MAX_BODY_BYTES + 10)
        yield b'"}'

    req = client.build_request("POST", "/api/audit", content=body(), headers={"content-type": "application/json"})
    seen["te"] = req.headers.get("transfer-encoding")
    seen["cl"] = req.headers.get("content-length")
    res = client.send(req)
    assert seen == {"te": "chunked", "cl": None}
    assert res.status_code == 413
    assert_security_headers(res, api=True)


def test_chunked_body_under_cap_still_works(client):
    def body():
        yield '{"article": "'.encode()
        yield "قال تعالى: ﴿اقرأ باسم ربك الذي خلق﴾".encode()
        yield b'"}'

    req = client.build_request("POST", "/api/audit", content=body(), headers={"content-type": "application/json"})
    assert req.headers.get("content-length") is None
    res = client.send(req)
    assert res.status_code == 200
    assert res.json()["findings"][0]["quote"] == "اقرأ باسم ربك الذي خلق"


def test_body_cap_covers_phrase_and_suggest(client):
    for path in ("/api/phrase", "/api/suggest"):
        req = client.build_request("POST", path, content=_chunks(MAX_BODY_BYTES + 1), headers={"content-type": "application/json"})
        assert client.send(req).status_code == 413


# --- list bounds and malformed JSON ---------------------------------------------------------------------------------

def test_phrase_others_and_fields_are_bounded(client):
    base = {"article": "قال تعالى اقرأ باسم ربك الذي خلق", "start": 10, "end": 32}
    assert client.post("/api/phrase", json={**base, "others": [[0, 1]] * 201}).status_code == 422
    assert client.post("/api/phrase", json={**base, "others": [[0, 1]] * 200}).status_code in (200, 400)
    assert client.post("/api/phrase", json={**base, "surah": 115}).status_code == 422
    assert client.post("/api/phrase", json={**base, "finding_id": 10_001}).status_code == 422
    assert client.post("/api/suggest", json={"before": "ا" * (MAX_BEFORE + 1)}).status_code == 422
    assert client.post("/api/suggest", json={"before": "ا", "after": "ا" * (MAX_AFTER + 1)}).status_code == 422


@pytest.mark.parametrize("payload", [
    b"[" * 40_000 + b"]" * 40_000,                                   # deep nesting, within the byte cap
    b'{"article": "x", "junk": ' + b"[" * 20_000 + b"]" * 20_000 + b"}",
    b'{"article": "x", "start": ' + b"9" * 30_000 + b', "end": 1}',   # a 30,000-digit integer
    b'{"article": "x", "start": 1e400, "end": 1}',                     # infinity
    b'{"article": "x", "start": -1e308, "end": 1e308}',
    b'{"article": "\\ud800", "start": 0, "end": 1}',                   # a lone surrogate
    b"\xff\xfe not json",
], ids=["deep-array", "deep-object", "huge-integer", "positive-infinity", "signed-infinity", "lone-surrogate", "invalid-utf8"])
def test_malformed_json_is_refused_without_500(client, payload):
    for path in ("/api/phrase", "/api/audit", "/api/suggest"):
        res = client.post(path, content=payload, headers={"content-type": "application/json"})
        assert 400 <= res.status_code < 500, (path, res.status_code)


# --- self-hosted fonts ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", HTML_FILES)
def test_pages_load_nothing_from_another_host(name):
    html = (STATIC / name).read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html
    for tag in re.findall(r"<(?:link|script|img|iframe|source)\b[^>]*>", html):
        for url in re.findall(r'(?:href|src)="([^"]+)"', tag):
            assert url.startswith(("/", "data:")), (name, tag)  # anchors to other sites are <a>, not resources
    assert 'lang="ar"' in html and 'dir="rtl"' in html
    assert "<style" not in html and " style=" not in html  # CSP style-src 'self' allows neither


def test_font_files_and_licences_are_present():
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    urls = re.findall(r'url\("(/static/fonts/[^"]+)"\)', css)
    assert len(urls) == 6
    for url in urls:
        path = STATIC / url.removeprefix("/static/")
        assert path.read_bytes()[:4] == b"wOF2", url
    assert css.count("font-display: swap") == 6
    total = 0
    for d in FONT_DIRS:
        lic = (STATIC / "fonts" / d / "OFL.txt").read_text(encoding="utf-8")
        assert "SIL Open Font License, Version 1.1" in lic
        total += sum(p.stat().st_size for p in (STATIC / "fonts" / d).glob("*.woff2"))
    assert total < 300_000  # six subsets, about 226 KB on 4 Oct 2026
    assert "fonts.googleapis.com" not in css and "@import" not in css
