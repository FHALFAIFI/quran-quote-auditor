"""With ACCOUNTS_ENABLED off (the default), nothing about accounts exists: no route, no script, no CSP change, and the
health answer only gains ``"accounts_enabled": false``. A half-configured flag behaves as off."""

import os
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from tests.accounts_helpers import SUPABASE_URL, accounts_main

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
ROUTES = [("GET", "/api/account/config"), ("GET", "/api/account/drafts"), ("POST", "/api/account/drafts"),
          ("GET", "/api/account/drafts/00000000-0000-4000-8000-000000000001"), ("PUT", "/api/account/drafts/00000000-0000-4000-8000-000000000001"),
          ("DELETE", "/api/account/drafts/00000000-0000-4000-8000-000000000001"), ("GET", "/api/account/preferences"),
          ("PUT", "/api/account/preferences"), ("GET", "/api/account/export"), ("DELETE", "/api/account"), ("POST", "/api/account/signout")]


def test_default_is_off_everywhere():
    assert os.environ.get("ACCOUNTS_ENABLED", "") in ("", "false", "0")
    import app.main as main

    client = TestClient(main.app)
    h = client.get("/api/health").json()
    assert h["accounts_enabled"] is False
    for method, path in ROUTES:
        r = client.request(method, path, json={}, headers={"Authorization": "Bearer x"})
        assert r.status_code == 404, (method, path, r.status_code)
    csp = client.get("/").headers["content-security-policy"]
    assert "connect-src 'self';" in csp and "supabase" not in csp
    assert not any(getattr(r, "path", "").startswith("/api/account") for r in main.app.routes)
    assert not hasattr(main.app.state, "accounts")


def test_health_keys_only_gain_the_flag():
    import app.main as main

    keys = set(TestClient(main.app).get("/api/health").json())
    assert keys == {"status", "mode", "ai_configured", "provider", "provider_name", "ai_selection", "ai_last_call", "max_chars",
                    "ai_max_chars", "ai_max_completion_tokens", "build", "source", "source_ok", "ai_recent", "accounts_enabled"}


def test_guest_page_has_no_account_code():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "account" not in html.lower() and "supabase" not in html.lower()
    app_js = (STATIC / "app.js").read_text(encoding="utf-8")
    # the only account reference in the guest script: load account.js when (and only when) the server says the flag is on
    assert app_js.count("/static/account.js") == 1
    assert re.search(r"if \(h\.accounts_enabled === true\) loadAccounts\(\);", app_js)
    for name in ("suggest-ui.js", "workspace.js", "revision.js", "surahs.js", "styles.css"):
        text = (STATIC / name).read_text(encoding="utf-8").lower()
        assert "supabase" not in text and "account" not in text, name
    for name in ("app.js",):
        assert "supabase" not in (STATIC / name).read_text(encoding="utf-8").lower()


def test_half_configured_flag_stays_off():
    for env in ({"SUPABASE_URL": ""}, {"SUPABASE_ANON_KEY": ""}, {"SUPABASE_URL": "http://project.example.com"}, {"SUPABASE_URL": "ftp://x"},
                {"SUPABASE_JWKS_URL": "http://keys.example.com/jwks.json"}, {"SUPABASE_JWKS_URL": "file:///tmp/jwks.json"}):
        saved = dict(os.environ)
        try:
            os.environ.update({"ACCOUNTS_ENABLED": "true", "SUPABASE_URL": SUPABASE_URL, "SUPABASE_ANON_KEY": "anon"})
            os.environ.update(env)
            from app.accounts.config import AccountConfig

            assert AccountConfig.from_env().enabled is False, env
        finally:
            os.environ.clear()
            os.environ.update(saved)


def test_flag_off_does_not_import_jwt_code():
    # app.main with the flag off imports only the stdlib config module of the accounts package
    import app.main  # noqa: F401

    src = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    assert "from .accounts.config import AccountConfig" in src
    assert re.search(r"if ACCOUNTS\.enabled:\n    from \.accounts\.api import install", src)


def test_reload_back_to_off_after_on():
    with accounts_main() as (main, ctx, keys, fake):
        assert TestClient(main.app).get("/api/health").json()["accounts_enabled"] is True
    import app.main as main2

    assert TestClient(main2.app).get("/api/health").json()["accounts_enabled"] is False
    assert TestClient(main2.app).get("/api/account/drafts").status_code == 404
    assert "app.accounts.api" in sys.modules   # loaded by the ON test only; the OFF app never registers it
