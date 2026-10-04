"""The account API with the flag ON, through FastAPI's TestClient, with MemoryStore (which enforces per-user isolation by
itself) and a fake JWKS. Covers roadmap Stage 2 acceptance tests 2 (isolation through the API), 3 (tokens), 6 (replay after
deletion), 8 (conflict), 9 (limits) and the no-content-in-logs rule.

NOT covered here: Row-Level Security in Postgres. There is no database in these tests; deploy/supabase/001_drafts.sql is
reviewed, not executed."""

import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.accounts_helpers import (
    ANON_KEY, SUPABASE_URL, USER_A, USER_B, Keys, accounts_main, hs256_token, tamper, token, unsigned_token,
)

SECRET_TEXT = "قال تعالى: إن مع العسر يسرا — نص-سري-للاختبار-٧٣٤١"


@pytest.fixture(scope="module")
def keys():
    return Keys()


@pytest.fixture
def env(keys):
    with accounts_main(keys=keys) as (main, ctx, k, fake):
        client = TestClient(main.app)
        ta, tb = token(keys, USER_A), token(keys, USER_B, alg="RS256")
        yield main, ctx, client, {"Authorization": f"Bearer {ta}"}, {"Authorization": f"Bearer {tb}"}


def new(client, h, body="نص", **kw):
    r = client.post("/api/account/drafts", json={"title": kw.pop("title", "مسودة"), "body": body, **kw}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_health_and_config(env):
    main, ctx, client, ha, hb = env
    h = client.get("/api/health").json()
    assert h["accounts_enabled"] is True
    cfg = client.get("/api/account/config").json()
    assert cfg == {"supabase_url": SUPABASE_URL, "anon_key": ANON_KEY, "max_drafts": 200, "max_chars": 20000}
    csp = client.get("/").headers["content-security-policy"]
    assert f"connect-src 'self' {SUPABASE_URL};" in csp


def test_round_trip(env):
    main, ctx, client, ha, hb = env
    d = new(client, ha, body=SECRET_TEXT, decisions={"findings": [{"id": 1, "changes": [{"decision": "approved"}]}]}, audited_text=SECRET_TEXT)
    assert d["version"] == 1 and d["length"] == len(SECRET_TEXT)
    lst = client.get("/api/account/drafts", headers=ha).json()["drafts"]
    assert [x["id"] for x in lst] == [d["id"]] and "body" not in lst[0]
    got = client.get(f"/api/account/drafts/{d['id']}", headers=ha).json()
    assert got["body"] == SECRET_TEXT and got["decisions"]["findings"][0]["changes"][0]["decision"] == "approved"
    up = client.put(f"/api/account/drafts/{d['id']}", json={"version": 1, "title": "اسم جديد"}, headers=ha).json()
    assert up["version"] == 2 and up["title"] == "اسم جديد" and up["body"] == SECRET_TEXT   # rename keeps the body
    exp = client.get("/api/account/export", headers=ha).json()
    assert exp["drafts"][0]["body"] == SECRET_TEXT and exp["preferences"] is None
    assert client.delete(f"/api/account/drafts/{d['id']}", headers=ha).status_code == 204
    assert client.get(f"/api/account/drafts/{d['id']}", headers=ha).status_code == 404


def test_preferences(env):
    main, ctx, client, ha, hb = env
    assert client.get("/api/account/preferences", headers=ha).json() == {"preferences": None}
    r = client.put("/api/account/preferences", json={"suggest_on": False, "distinct_on": True}, headers=ha).json()["preferences"]
    assert r["suggest_on"] is False and r["distinct_on"] is True
    assert client.get("/api/account/preferences", headers=hb).json() == {"preferences": None}


# ------------------------------------------------------------------------------------------------------- isolation (2)
def test_b_cannot_reach_a(env):
    main, ctx, client, ha, hb = env
    a = new(client, ha, body=SECRET_TEXT)
    client.put("/api/account/preferences", json={"suggest_on": False, "distinct_on": True}, headers=ha)
    url = f"/api/account/drafts/{a['id']}"
    for method, kw in (("GET", {}), ("PUT", {"json": {"version": 1, "body": "اختراق"}}), ("DELETE", {})):
        r = client.request(method, url, headers=hb, **kw)
        assert r.status_code == 404, (method, r.status_code)
        assert SECRET_TEXT not in r.text and a["id"] not in r.text
    assert client.get("/api/account/drafts", headers=hb).json()["drafts"] == []
    exp = client.get("/api/account/export", headers=hb).json()
    assert exp["drafts"] == [] and exp["preferences"] is None and SECRET_TEXT not in str(exp)
    assert client.get("/api/account/preferences", headers=hb).json() == {"preferences": None}
    # A's draft is untouched
    got = client.get(url, headers=ha).json()
    assert got["body"] == SECRET_TEXT and got["version"] == 1


def test_not_found_is_identical_for_missing_and_foreign(env):
    main, ctx, client, ha, hb = env
    a = new(client, ha)
    foreign = client.get(f"/api/account/drafts/{a['id']}", headers=hb)
    missing = client.get(f"/api/account/drafts/{uuid.uuid4()}", headers=hb)
    malformed = client.get("/api/account/drafts/1%20or%201=1", headers=hb)
    assert foreign.status_code == missing.status_code == malformed.status_code == 404
    assert foreign.json() == missing.json() == malformed.json()


def test_guessing_ids(env):
    main, ctx, client, ha, hb = env
    new(client, ha)
    for _ in range(50):
        assert client.get(f"/api/account/drafts/{uuid.uuid4()}", headers=hb).status_code == 404
    for guess in ("1", "0", "%2e%2e", "a" * 36, "00000000-0000-0000-0000-000000000000"):
        assert client.get(f"/api/account/drafts/{guess}", headers=hb).status_code == 404


def test_user_id_in_body_or_query_is_ignored(env):
    main, ctx, client, ha, hb = env
    # A sends B's id in the body: the draft is A's
    d = new(client, ha, body="لـ أ", user_id=USER_B)
    assert client.get(f"/api/account/drafts/{d['id']}", headers=hb).status_code == 404
    assert client.get(f"/api/account/drafts/{d['id']}", headers=ha).status_code == 200
    # B asks for A's list with A's id in the query string: B gets B's (empty) list
    assert client.get(f"/api/account/drafts?user_id={USER_A}", headers=hb).json()["drafts"] == []
    assert client.get(f"/api/account/export?user_id={USER_A}&sub={USER_A}", headers=hb).json()["drafts"] == []
    # A update with B's id in the body cannot move the draft to B
    client.put(f"/api/account/drafts/{d['id']}", json={"version": 1, "user_id": USER_B, "body": "ما زال لـ أ"}, headers=ha)
    assert client.get("/api/account/drafts", headers=hb).json()["drafts"] == []
    assert client.get(f"/api/account/drafts/{d['id']}", headers=ha).json()["body"] == "ما زال لـ أ"
    # a user id in the path is not a route
    assert client.get(f"/api/account/{USER_A}/drafts", headers=hb).status_code == 404


def test_replay_after_signout(env, keys):
    main, ctx, client, ha, hb = env
    other = {"Authorization": f"Bearer {token(keys, USER_A, alg='RS256')}"}   # a second session of A
    assert client.get("/api/account/drafts", headers=other).status_code == 200
    assert client.post("/api/account/signout", headers=other).status_code == 204
    r = client.get("/api/account/drafts", headers=other)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert client.get("/api/account/drafts", headers=ha).status_code == 200   # another session of A is unaffected


def test_replay_after_deletion(env, keys):
    main, ctx, client, ha, hb = env
    d = new(client, ha, body=SECRET_TEXT)
    new(client, hb, body="لـ ب")
    r = client.delete("/api/account", headers=ha)
    assert r.status_code == 200 and r.json() == {"deleted_drafts": 1, "auth_user_deleted": False}   # no service-role key set
    for path in ("/api/account/drafts", "/api/account/export", f"/api/account/drafts/{d['id']}", "/api/account/preferences"):
        assert client.get(path, headers=ha).status_code == 401, path
    fresh_a = {"Authorization": f"Bearer {token(keys, USER_A, alg='RS256')}"}   # another token of A, still valid at the provider
    assert client.get("/api/account/export", headers=fresh_a).status_code == 401
    # On another instance (empty denylist) the token is valid but finds nothing: empty, never someone else's rows
    ctx.denylist = type(ctx.denylist)()
    assert client.get("/api/account/export", headers=ha).json()["drafts"] == []
    assert len(client.get("/api/account/drafts", headers=hb).json()["drafts"]) == 1   # B unaffected


def test_no_or_bad_token_is_401(env, keys):
    main, ctx, client, ha, hb = env
    good = ha["Authorization"].split()[1]
    for h in ({}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer "}, {"Authorization": f"Bearer {unsigned_token()}"},
              {"Authorization": f"Bearer {hs256_token(keys.public_pem())}"}, {"Authorization": f"Bearer {tamper(good, sub=USER_B)}"},
              {"Authorization": f"Bearer {token(keys, exp=1, iat=0)}"}, {"Authorization": f"Bearer {token(keys, aud='x')}"}):
        for method, path in (("GET", "/api/account/drafts"), ("GET", "/api/account/export"), ("DELETE", "/api/account"),
                             ("PUT", "/api/account/preferences"), ("POST", "/api/account/drafts")):
            r = client.request(method, path, headers=h, json={"body": "x", "suggest_on": True, "distinct_on": True})
            assert r.status_code == 401, (h, method, path, r.status_code)
            assert "سجّل الدخول من جديد" in r.json()["error"]


# --------------------------------------------------------------------------------------------------------- conflict (8)
def test_conflict_409_never_overwrites(env):
    main, ctx, client, ha, hb = env
    d = new(client, ha, body="الأصل")
    url = f"/api/account/drafts/{d['id']}"
    tab1 = client.put(url, json={"version": 1, "body": "من التبويب الأول"}, headers=ha)
    assert tab1.status_code == 200 and tab1.json()["version"] == 2
    tab2 = client.put(url, json={"version": 1, "body": "من التبويب الثاني"}, headers=ha)
    assert tab2.status_code == 409
    j = tab2.json()
    assert j["code"] == "conflict" and j["yours"]["version"] == 1 and j["saved"]["version"] == 2 and j["saved"]["id"] == d["id"]
    assert "body" not in j["saved"]
    assert client.get(url, headers=ha).json()["body"] == "من التبويب الأول"
    # the writer chose to keep the second tab's copy: an explicit save with the current version
    keep = client.put(url, json={"version": 2, "body": "من التبويب الثاني"}, headers=ha)
    assert keep.status_code == 200 and keep.json()["version"] == 3


def test_put_requires_version(env):
    main, ctx, client, ha, hb = env
    d = new(client, ha)
    assert client.put(f"/api/account/drafts/{d['id']}", json={"body": "بلا نسخة"}, headers=ha).status_code == 422
    assert client.get(f"/api/account/drafts/{d['id']}", headers=ha).json()["body"] == "نص"


# ----------------------------------------------------------------------------------------------------------- limits (9)
def test_size_limits(env):
    main, ctx, client, ha, hb = env
    r = client.post("/api/account/drafts", json={"body": "ب" * 20001}, headers=ha)
    assert r.status_code == 413 and "٢٠٬٠٠٠" in r.json()["error"] and "نصّك باقٍ في المحرر" in r.json()["error"]
    assert client.post("/api/account/drafts", json={"body": "ب" * 20000}, headers=ha).status_code == 201
    assert client.post("/api/account/drafts", json={"body": "x", "title": "ع" * 201}, headers=ha).status_code == 400
    assert client.post("/api/account/drafts", json={"body": "x", "decisions": {"k": "ق" * 150_000}}, headers=ha).status_code == 413
    d = new(client, ha)
    assert client.put(f"/api/account/drafts/{d['id']}", json={"version": 1, "body": "ب" * 20001}, headers=ha).status_code == 413
    assert client.post("/api/account/drafts", content=b"{" + b" " * 700_000 + b"}", headers={**ha, "content-type": "application/json"}).status_code == 413


def test_count_limit(env):
    main, ctx, client, ha, hb = env
    for i in range(200):
        assert client.post("/api/account/drafts", json={"body": str(i)}, headers=ha).status_code == 201
    r = client.post("/api/account/drafts", json={"body": "٢٠١"}, headers=ha)
    assert r.status_code == 400 and r.json()["code"] == "draft_limit" and "٢٠٠" in r.json()["error"]
    assert client.post("/api/account/drafts", json={"body": "لـ ب"}, headers=hb).status_code == 201   # per user


def test_rate_limited(keys):
    with accounts_main({"ACCOUNT_RATE_LIMIT_PER_MINUTE": "5"}, keys=keys) as (main, ctx, _, fake):
        client = TestClient(main.app)
        h = {"Authorization": f"Bearer {token(keys)}", "X-Forwarded-For": "203.0.113.9"}
        codes = [client.get("/api/account/drafts", headers=h).status_code for _ in range(7)]
        assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]


def test_delete_account_with_service_role_key(keys):
    import httpx

    from app.accounts.store import AdminClient

    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(204 if req.method == "DELETE" else 201)

    with accounts_main({"SUPABASE_SERVICE_ROLE_KEY": "service-SECRET"}, keys=keys) as (main, ctx, _, fake):
        ctx.admin = AdminClient(SUPABASE_URL, client=httpx.Client(transport=httpx.MockTransport(handler)))
        client = TestClient(main.app)
        h = {"Authorization": f"Bearer {token(keys)}"}
        new(client, h, body=SECRET_TEXT)
        r = client.delete("/api/account", headers=h)
        assert r.json() == {"deleted_drafts": 1, "auth_user_deleted": True}
        assert "service-SECRET" not in r.text
        assert seen[0].method == "DELETE" and seen[0].url.path == f"/auth/v1/admin/users/{USER_A}"
        assert seen[1].url.path == "/rest/v1/deletion_log"
        logged = seen[1].content.decode()
        assert USER_A not in logged and SECRET_TEXT not in logged and "user_hash" in logged


# ------------------------------------------------------------------------------------------------------------------ logs
def test_logs_hold_no_text_or_token(env, caplog):
    main, ctx, client, ha, hb = env
    caplog.set_level(logging.DEBUG)
    tok = ha["Authorization"].split()[1]
    d = new(client, ha, body=SECRET_TEXT, title="عنوان-سري-٩٩", decisions={"q": SECRET_TEXT}, audited_text=SECRET_TEXT)
    client.get(f"/api/account/drafts/{d['id']}", headers=ha)
    client.put(f"/api/account/drafts/{d['id']}", json={"version": 1, "body": SECRET_TEXT + "!"}, headers=ha)
    client.put(f"/api/account/drafts/{d['id']}", json={"version": 1, "body": SECRET_TEXT + "?"}, headers=ha)   # 409
    client.get(f"/api/account/drafts/{d['id']}", headers=hb)    # 404
    client.post("/api/account/drafts", json={"body": SECRET_TEXT * 2000}, headers=ha)   # 413
    client.get("/api/account/export", headers=ha)
    client.get("/api/account/drafts", headers={"Authorization": f"Bearer {tamper(tok, sub=USER_B)}"})   # 401
    text = caplog.text
    assert SECRET_TEXT not in text and "عنوان-سري" not in text and "نص-سري" not in text
    assert tok not in text and tok.split(".")[1] not in text and tok.split(".")[2] not in text
    assert f"id={d['id']} status=409" in text and f"id={d['id']} status=404" in text and "status=401" in text
