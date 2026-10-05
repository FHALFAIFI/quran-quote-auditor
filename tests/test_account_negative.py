"""Negative tests of the account API (security review of 5 Oct), flag ON, nothing sent to the network.

Two back ends:
- MemoryStore wrapped in a counter, to show that a refused token never reaches the store at all;
- PostgrestStore against scripts/fake_supabase.py started in this process on 127.0.0.1 — a LOCAL FAKE of Supabase Auth and
  PostgREST (its row filtering is a Python imitation of RLS, not Postgres; the SQL policies are tested in
  tests/test_account_rls_pg.py). The server verifies the fake's tokens through its JWKS over loopback, as in production.

Every draft text and title below carries a Latin marker as well as Arabic: the log scrubber (app/logging_safety.py) removes
long Arabic runs from every record, so an Arabic-only check could pass even if a handler logged the draft."""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import threading
import time
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from tests.accounts_helpers import (
    ISSUER, USER_A, USER_B, Keys, accounts_main, hs256_token, tamper, token, unsigned_token,
)

ROOT = Path(__file__).resolve().parents[1]
MARK = "DRAFTMARK-q7Z3"
SECRET = f"{MARK} إن مع العسر يسرا"
TITLE = f"TITLEMARK-k2 عنوان"


@pytest.fixture(scope="module")
def keys():
    return Keys()


class CountingStore:
    """Passes every call to the real store and records its name."""

    def __init__(self, inner):
        self.inner, self.calls = inner, []

    def __getattr__(self, name):
        fn = getattr(self.inner, name)

        def wrapped(*a, **kw):
            self.calls.append(name)
            return fn(*a, **kw)
        return wrapped


@pytest.fixture
def env(keys):
    from app.accounts.store import MemoryStore

    store = CountingStore(MemoryStore())
    with accounts_main(keys=keys, store=store) as (main, ctx, k, fake):
        yield main, ctx, TestClient(main.app), store


def bearer(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def bad_tokens(keys) -> dict[str, str]:
    from cryptography.hazmat.primitives.asymmetric import rsa

    now = int(time.time())
    good = token(keys)
    h, p, s = good.split(".")
    no_kid = jwt.encode({"sub": USER_A, "aud": "authenticated", "iss": ISSUER, "iat": now, "exp": now + 3600, "role": "authenticated"},
                        keys.ec, algorithm="ES256")
    return {
        "expired": token(keys, exp=now - 3600, iat=now - 7200),
        "not_yet_valid_nbf": token(keys, nbf=now + 3600),
        "issued_in_the_future": token(keys, iat=now + 3600),
        "alg_none": unsigned_token(),
        "alg_none_no_kid": unsigned_token(kid=""),
        "wrong_audience": token(keys, aud="anon"),
        "wrong_issuer": token(keys, iss="https://evil.example/auth/v1"),
        "tampered_signature": f"{h}.{p}.{s[:8]}{'A' if s[8] != 'A' else 'B'}{s[9:]}",
        "tampered_payload_sub": tamper(good, sub=USER_B),
        "wrong_key_same_kid": token(keys, kid="ec-1", key=keys.other_ec),
        "wrong_rsa_key_same_kid": token(keys, alg="RS256", kid="rsa-1", key=rsa.generate_private_key(public_exponent=65537, key_size=2048)),
        "hs256_with_ec_public_pem": hs256_token(keys.public_pem("ec")),
        "hs256_with_rsa_public_pem": hs256_token(keys.public_pem("rsa"), kid="rsa-1"),
        "hs256_with_public_jwk_text": hs256_token(json.dumps(keys.jwks()["keys"][0]).encode()),
        "no_kid": no_kid,
        "service_role_claim": token(keys, role="service_role"),
        "anon_key_as_token": "anon-public-test-key",
    }


ROUTES = [
    ("GET", "/api/account/drafts", None),
    ("POST", "/api/account/drafts", {"body": SECRET, "title": TITLE}),
    ("GET", "/api/account/drafts/{id}", None),
    ("PUT", "/api/account/drafts/{id}", {"version": 1, "body": SECRET}),
    ("DELETE", "/api/account/drafts/{id}", None),
    ("GET", "/api/account/export", None),
    ("GET", "/api/account/preferences", None),
    ("PUT", "/api/account/preferences", {"suggest_on": True, "distinct_on": True}),
    ("POST", "/api/account/signout", None),
    ("DELETE", "/api/account", None),
]


# --------------------------------------------------------------------------------------------------------------- tokens
def test_every_bad_token_is_401_on_every_route_and_never_reaches_the_store(env, keys):
    main, ctx, client, store = env
    d = client.post("/api/account/drafts", json={"body": SECRET}, headers=bearer(token(keys))).json()
    store.calls.clear()
    answers = set()
    for name, bad in bad_tokens(keys).items():
        for method, path, body in ROUTES:
            r = client.request(method, path.format(id=d["id"]), headers=bearer(bad), json=body)
            assert r.status_code == 401, (name, method, path, r.status_code)
            assert r.headers["www-authenticate"] == "Bearer"
            answers.add(r.text)
    assert store.calls == [], store.calls          # no read, no write, no delete with a refused token
    assert len(answers) == 1                       # the same answer whatever the reason: no oracle on why
    # A's draft and account are intact
    got = client.get(f"/api/account/drafts/{d['id']}", headers=bearer(token(keys)))
    assert got.status_code == 200 and got.json()["body"] == SECRET


# --------------------------------------------------------------------------------------------------- existence leaks
def _shape(r: httpx.Response):
    return r.status_code, r.text, sorted((k, v) for k, v in r.headers.items() if k not in ("date", "content-length"))


def test_foreign_missing_and_malformed_ids_answer_identically_on_every_method(env, keys):
    main, ctx, client, store = env
    ha, hb = bearer(token(keys, USER_A)), bearer(token(keys, USER_B))
    a = client.post("/api/account/drafts", json={"body": SECRET, "title": TITLE}, headers=ha).json()
    for method, body in (("GET", None), ("PUT", {"version": 1, "body": "x"}), ("DELETE", None)):
        foreign = client.request(method, f"/api/account/drafts/{a['id']}", headers=hb, json=body)
        missing = client.request(method, f"/api/account/drafts/{uuid.uuid4()}", headers=hb, json=body)
        malformed = client.request(method, "/api/account/drafts/not-a-uuid", headers=hb, json=body)
        assert foreign.status_code == 404, (method, foreign.status_code)   # a matching version must not turn into 409
        assert _shape(foreign) == _shape(missing) == _shape(malformed), method
        assert MARK not in foreign.text and a["id"] not in foreign.text
    # after A deletes it, B's answer is still the same
    before = _shape(client.get(f"/api/account/drafts/{a['id']}", headers=hb))
    assert client.delete(f"/api/account/drafts/{a['id']}", headers=ha).status_code == 204
    assert _shape(client.get(f"/api/account/drafts/{a['id']}", headers=hb)) == before
    assert client.get(f"/api/account/drafts/{a['id']}", headers=ha).json() == client.get(f"/api/account/drafts/{a['id']}", headers=hb).json()


def test_user_id_swapped_in_the_query_string_on_id_routes(env, keys):
    main, ctx, client, store = env
    ha, hb = bearer(token(keys, USER_A)), bearer(token(keys, USER_B))
    a = client.post("/api/account/drafts", json={"body": SECRET}, headers=ha).json()
    q = f"?user_id={USER_A}&sub={USER_A}&user_id=eq.{USER_A}"
    for method, body in (("GET", None), ("PUT", {"version": 1, "body": "اختراق"}), ("DELETE", None)):
        assert client.request(method, f"/api/account/drafts/{a['id']}{q}", headers=hb, json=body).status_code == 404, method
    assert client.put(f"/api/account/preferences{q}", json={"suggest_on": False, "distinct_on": False}, headers=hb).status_code == 200
    assert client.get("/api/account/preferences", headers=ha).json() == {"preferences": None}   # B's write stayed B's
    assert client.delete(f"/api/account{q}", headers=hb).json()["deleted_drafts"] == 0             # B deleted B, not A
    got = client.get(f"/api/account/drafts/{a['id']}", headers=ha).json()
    assert got["body"] == SECRET and got["version"] == 1


def test_body_cannot_set_owner_or_server_fields(env, keys):
    main, ctx, client, store = env
    ha, hb = bearer(token(keys, USER_A)), bearer(token(keys, USER_B))
    forged_id = str(uuid.uuid4())
    d = client.post("/api/account/drafts", headers=ha, json={"body": SECRET, "id": forged_id, "user_id": USER_B, "sub": USER_B,
                                                            "version": 77, "created_at": "2000-01-01T00:00:00+00:00", "body_length": 1}).json()
    assert d["id"] != forged_id and d["version"] == 1 and d["created_at"] > "2001" and d["length"] == len(SECRET)
    up = client.put(f"/api/account/drafts/{d['id']}", headers=ha, json={"version": 1, "id": forged_id, "user_id": USER_B, "body": "ب"}).json()
    assert up["id"] == d["id"] and up["version"] == 2
    assert client.get("/api/account/drafts", headers=hb).json()["drafts"] == []


def test_a_full_size_draft_passes_the_request_cap_and_one_byte_over_does_not(env, keys):
    """After the rebase onto main's SecurityMiddleware: /api/account/ keeps its own cap (600,000 bytes), larger than the
    audit's, so a draft at every field's limit is saved; anything over the cap is refused before it is read."""
    main, ctx, client, store = env
    full = {"body": "ب" * 20000, "audited_text": "ت" * 20000, "decisions": {"k": "ق" * 99_000}, "title": "ع" * 200}
    r = client.post("/api/account/drafts", json=full, headers=bearer(token(keys)))
    assert r.status_code == 201, r.text
    raw = json.dumps(full, ensure_ascii=False).encode()
    assert len(raw) > main.MAX_BODY_BYTES                     # more than an audit may send
    pad = b" " * (main.ACCOUNT_MAX_BODY_BYTES - len(raw) + 1)
    over = client.post("/api/account/drafts", content=raw[:-1] + pad + b"}", headers={**bearer(token(keys)), "content-type": "application/json"})
    assert over.status_code == 413
    assert client.post("/api/audit", content=raw, headers={"content-type": "application/json"}).status_code == 413   # audit cap unchanged


# ------------------------------------------------------------------------------------------------------------ logs
def test_no_text_or_token_in_logs_on_negative_paths(env, keys, caplog):
    main, ctx, client, store = env
    caplog.set_level(logging.DEBUG)
    good_a, good_b = token(keys, USER_A), token(keys, USER_B)
    a = client.post("/api/account/drafts", json={"body": SECRET, "title": TITLE, "decisions": {"q": SECRET}, "audited_text": SECRET},
                    headers=bearer(good_a)).json()
    tokens = [good_a, good_b, *bad_tokens(keys).values()]
    for bad in tokens[2:]:
        client.put(f"/api/account/drafts/{a['id']}", json={"version": 1, "body": SECRET}, headers=bearer(bad))
    client.get(f"/api/account/drafts/{a['id']}?user_id={USER_A}", headers=bearer(good_b))
    client.put(f"/api/account/drafts/{a['id']}", json={"version": 1, "body": SECRET + "1"}, headers=bearer(good_a))
    client.put(f"/api/account/drafts/{a['id']}", json={"version": 1, "body": SECRET + "2"}, headers=bearer(good_a))   # 409
    client.post("/api/account/drafts", json={"body": SECRET * 1000}, headers=bearer(good_a))                       # 413
    client.post("/api/account/drafts", json={"body": SECRET, "title": TITLE * 20}, headers=bearer(good_a))          # 400
    client.get("/api/account/export", headers=bearer(good_a))
    client.delete("/api/account", headers=bearer(good_a))
    client.get("/api/account/drafts", headers=bearer(good_a))                                                      # 401 after deletion
    text = caplog.text
    assert MARK not in text and "TITLEMARK" not in text
    for t in tokens:
        for part in t.split("."):
            if len(part) >= 16:
                assert part not in text
    assert "status=401" in text and "status=409" in text and "status=404" in text


def test_postgrest_error_details_never_reach_the_answer_or_the_logs(keys, caplog):
    """PostgREST puts the failing row in ``details`` for a check violation; that row is the draft. It must not be echoed."""
    from app.accounts.store import PostgrestStore

    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, json=[])
        return httpx.Response(400, json={"code": "23514", "message": "new row for relation \"drafts\" violates check constraint",
                                         "details": f"Failing row contains ({SECRET}, {TITLE}).", "hint": None})

    with accounts_main(keys=keys) as (main, ctx, _, fake):
        ctx.store = PostgrestStore("https://test-project.supabase.example", "anon", client=httpx.Client(transport=httpx.MockTransport(handler)))
        caplog.set_level(logging.DEBUG)
        r = TestClient(main.app).post("/api/account/drafts", json={"body": SECRET, "title": TITLE}, headers=bearer(token(keys)))
        assert r.status_code == 400 and r.json()["code"] == "limit"
        assert MARK not in r.text and "TITLEMARK" not in r.text and "Failing row" not in r.text
        assert MARK not in caplog.text and "Failing row" not in caplog.text


# ------------------------------------------------------------------------------- PostgrestStore + local fake Supabase
def _load_fake():
    spec = importlib.util.spec_from_file_location("fake_supabase_inproc", ROOT / "scripts" / "fake_supabase.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fake_supabase():
    fake = _load_fake()
    fake.ARGS = argparse.Namespace(port=0, anon="fake-anon-key", service="fake-service-role-key", allow_redirect="http://127.0.0.1:")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), fake.Handler)
    fake.BASE = f"http://127.0.0.1:{srv.server_address[1]}"
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield fake
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture
def live(fake_supabase):
    """app.main with the flag on, wired exactly as install() wires it (JWKSCache over loopback, PostgrestStore, AdminClient),
    against the in-process fake."""
    from app.accounts.store import AdminClient, PostgrestStore
    from app.accounts.tokens import JWKSCache, TokenVerifier

    env = {"SUPABASE_URL": fake_supabase.BASE, "SUPABASE_ANON_KEY": "fake-anon-key", "SUPABASE_SERVICE_ROLE_KEY": "fake-service-role-key"}
    with accounts_main(env) as (main, ctx, _, __):
        cfg = ctx.cfg
        ctx.verifier = TokenVerifier(JWKSCache(cfg.jwks_url, cfg.jwks_ttl, cfg.jwks_min_refetch), cfg.issuer, cfg.audience, cfg.leeway)
        ctx.store = PostgrestStore(cfg.supabase_url, cfg.anon_key)
        ctx.admin = AdminClient(cfg.supabase_url)
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        fake_supabase.STATE["users"].update({"a@example.test": a, "b@example.test": b})
        ta, tb = fake_supabase.mint(a, "a@example.test")[0], fake_supabase.mint(b, "b@example.test")[0]
        yield main, ctx, TestClient(main.app), fake_supabase, (a, bearer(ta)), (b, bearer(tb))


def test_postgrest_cross_user_conflict_and_deletion(live):
    main, ctx, client, fake, (a, ha), (b, hb) = live
    ids = [client.post("/api/account/drafts", json={"body": f"{SECRET} {i}", "title": TITLE}, headers=ha).json()["id"] for i in range(2)]
    assert client.put("/api/account/preferences", json={"suggest_on": False, "distinct_on": True}, headers=ha).status_code == 200
    b1 = client.post("/api/account/drafts", json={"body": "لـ ب"}, headers=hb).json()["id"]
    # B: A's ids answer like a random id; B's list and export hold only B's draft
    for method, body in (("GET", None), ("PUT", {"version": 1, "body": "اختراق"}), ("DELETE", None)):
        foreign = client.request(method, f"/api/account/drafts/{ids[0]}?user_id={a}", headers=hb, json=body)
        missing = client.request(method, f"/api/account/drafts/{uuid.uuid4()}", headers=hb, json=body)
        assert foreign.status_code == missing.status_code == 404 and foreign.json() == missing.json(), method
    exp_b = client.get("/api/account/export", headers=hb).json()
    assert [d["id"] for d in exp_b["drafts"]] == [b1] and MARK not in json.dumps(exp_b) and exp_b["preferences"] is None
    # two tabs of A: the stale save is refused and overwrites nothing
    url = f"/api/account/drafts/{ids[0]}"
    assert client.put(url, json={"version": 1, "body": "التبويب الأول"}, headers=ha).status_code == 200
    stale = client.put(url, json={"version": 1, "body": "التبويب الثاني"}, headers=ha)
    assert stale.status_code == 409 and stale.json()["saved"]["version"] == 2 and "body" not in stale.json()["saved"]
    assert client.get(url, headers=ha).json()["body"] == "التبويب الأول"
    # A deletes the account: every row of A goes, B's stays, A's token no longer works here
    r = client.delete("/api/account", headers=ha)
    assert r.status_code == 200 and r.json() == {"deleted_drafts": 2, "auth_user_deleted": True}
    state = fake.STATE
    assert not state["drafts"].get(a) and a not in state["prefs"] and a not in state["users"].values()
    assert list(state["drafts"][b]) == [b1]
    assert len(state["deletion_log"]) == 1 and a not in json.dumps(state["deletion_log"])
    for method, path, body in ROUTES:
        assert client.request(method, path.format(id=ids[1]), headers=ha, json=body).status_code == 401, (method, path)
    assert client.get("/api/account/drafts", headers=hb).json()["drafts"][0]["id"] == b1
    # the requests the server sent to the fake's PostgREST all carried a user's own token, never the service key
    rest = [x for x in state["requests"] if x["path"].startswith("/rest/v1/drafts") or x["path"].startswith("/rest/v1/preferences")]
    assert rest and all(x["auth"] == "user" for x in rest)
