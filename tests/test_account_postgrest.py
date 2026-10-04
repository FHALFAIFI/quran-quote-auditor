"""PostgrestStore against an httpx MockTransport: what it sends (the WRITER'S token and the anon key; never the service-role
key; every query filtered by the verified user id) and how it maps PostgREST errors.

This is a unit test of the HTTP calls. It does NOT test Row-Level Security: there is no Postgres here, and the policies in
deploy/supabase/001_drafts.sql have been reviewed, not executed."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.accounts.store import AuthRejected, Conflict, LimitReached, NotFound, PostgrestStore, Unavailable
from app.accounts.tokens import Principal
from tests.accounts_helpers import ANON_KEY, SERVICE_KEY, SUPABASE_URL, USER_A, Keys, accounts_main, token

P = Principal(user_id=USER_A, token="user-a-access-token", expires_at=2**31)
ROW = {"id": "11111111-1111-4111-8111-111111111111", "title": "t", "body": "b", "decisions": None, "audited_text": None,
       "created_at": "2026-10-04T00:00:00+00:00", "updated_at": "2026-10-04T00:00:00+00:00", "version": 1, "body_length": 1}


class Recorder:
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []

    def __call__(self, req: httpx.Request):
        self.requests.append(req)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        status, body = r
        return httpx.Response(status, json=body) if body is not None else httpx.Response(status)


def store(*responses):
    rec = Recorder(responses)
    return PostgrestStore(SUPABASE_URL, ANON_KEY, client=httpx.Client(transport=httpx.MockTransport(rec))), rec


def assert_user_headers(req, tok="user-a-access-token"):
    assert req.headers["apikey"] == ANON_KEY
    assert req.headers["authorization"] == f"Bearer {tok}"
    assert SERVICE_KEY not in str(req.headers) and "service" not in str(req.headers).lower()


def test_every_call_uses_the_users_token_and_filters_by_user():
    s, rec = store((200, [ROW]), (200, [ROW]), (201, [ROW]), (200, [ROW]), (200, [ROW]), (200, [ROW]), (200, []), (201, [{"suggest_on": True, "distinct_on": False}]),
                   (200, [ROW]), (204, None))
    s.list(P); s.all(P); s.create(P, {"title": "t", "body": "b", "user_id": "evil", "version": 99, "id": "x"}); s.get(P, ROW["id"])
    s.update(P, ROW["id"], 1, {"body": "c", "user_id": "evil"}); s.delete(P, ROW["id"]); s.get_prefs(P)
    s.put_prefs(P, {"suggest_on": True, "distinct_on": False}); s.delete_all(P)
    assert len(rec.requests) == 10
    for req in rec.requests:
        assert_user_headers(req)
        assert req.url.host == "test-project.supabase.example" and req.url.path.startswith("/rest/v1/")
        q = dict(req.url.params)
        if req.method == "POST":   # an insert names the verified user in the row (RLS's with-check compares it with auth.uid())
            assert json.loads(req.content)["user_id"] == USER_A
        else:
            assert q.get("user_id") == f"eq.{USER_A}", (req.method, req.url)
    create = json.loads(rec.requests[2].content)
    assert create == {"title": "t", "body": "b", "user_id": USER_A}   # only whitelisted fields; the verified id, not "evil"
    patch = rec.requests[4]
    assert patch.method == "PATCH" and dict(patch.url.params)["version"] == "eq.1" and json.loads(patch.content) == {"body": "c"}
    assert rec.requests[4].headers["prefer"] == "return=representation"
    prefs = rec.requests[7]
    assert json.loads(prefs.content)["user_id"] == USER_A and "merge-duplicates" in prefs.headers["prefer"]


def test_list_does_not_fetch_bodies():
    s, rec = store((200, [ROW]))
    s.list(P)
    assert "body," not in rec.requests[0].url.params["select"] and "body_length" in rec.requests[0].url.params["select"]


@pytest.mark.parametrize("status,body,exc", [
    (401, {"code": "PGRST301", "message": "JWT expired"}, AuthRejected),
    (401, {"code": "PGRST303", "message": "JWT expired"}, AuthRejected),
    (400, {"code": "23514", "message": "new row violates check constraint"}, LimitReached),
    (400, {"code": "P0001", "message": "draft_limit"}, LimitReached),
    (403, {"code": "42501", "message": "new row violates row-level security policy"}, NotFound),
    (400, {"code": "22P02", "message": "invalid input syntax for type uuid"}, NotFound),
    (500, {"code": "XX000", "message": "internal"}, Unavailable),
    (502, None, Unavailable),
])
def test_error_mapping(status, body, exc):
    s, _ = store((status, body))
    with pytest.raises(exc):
        s.create(P, {"body": "x"})


def test_network_error_is_unavailable():
    s, _ = store(httpx.ConnectError("down"))
    with pytest.raises(Unavailable):
        s.list(P)


def test_get_missing_is_not_found():
    s, _ = store((200, []))
    with pytest.raises(NotFound):
        s.get(P, ROW["id"])


def test_stale_version_is_conflict_with_saved_metadata():
    s, rec = store((200, []), (200, [{**ROW, "version": 3}]))
    with pytest.raises(Conflict) as e:
        s.update(P, ROW["id"], 1, {"body": "c"})
    assert e.value.current["version"] == 3 and "body" not in e.value.current
    assert rec.requests[1].method == "GET"


def test_update_of_missing_or_foreign_is_not_found():
    s, _ = store((200, []), (200, []))
    with pytest.raises(NotFound):
        s.update(P, ROW["id"], 1, {"body": "c"})


def test_delete_of_missing_is_not_found():
    s, _ = store((200, []))
    with pytest.raises(NotFound):
        s.delete(P, ROW["id"])


def test_api_forwards_the_verified_users_own_token(monkeypatch):
    """Through the API: the token PostgREST receives is exactly the writer's, and the service-role key never leaves the
    server's admin path even when it is configured."""
    keys = Keys()
    with accounts_main({"SUPABASE_SERVICE_ROLE_KEY": SERVICE_KEY}, keys=keys) as (main, ctx, _, fake):
        s, rec = store((200, [ROW]), (200, [ROW]))
        ctx.store = s
        tok = token(keys)
        client = TestClient(main.app)
        assert client.get("/api/account/drafts", headers={"Authorization": f"Bearer {tok}"}).status_code == 200
        r = client.get(f"/api/account/drafts/{ROW['id']}", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200 and SERVICE_KEY not in r.text
        for req in rec.requests:
            assert_user_headers(req, tok)
        cfg = client.get("/api/account/config").text
        assert SERVICE_KEY not in cfg and ANON_KEY in cfg


def test_api_maps_store_auth_refusal_to_401():
    keys = Keys()
    with accounts_main(keys=keys) as (main, ctx, _, fake):
        s, _ = store((401, {"code": "PGRST303", "message": "JWT expired"}))
        ctx.store = s
        r = TestClient(main.app).get("/api/account/drafts", headers={"Authorization": f"Bearer {token(keys)}"})
        assert r.status_code == 401 and "سجّل الدخول من جديد" in r.json()["error"]


def test_api_maps_store_outage_to_503():
    keys = Keys()
    with accounts_main(keys=keys) as (main, ctx, _, fake):
        s, _ = store(httpx.ConnectError("down"))
        ctx.store = s
        r = TestClient(main.app).post("/api/account/drafts", json={"body": "نص"}, headers={"Authorization": f"Bearer {token(keys)}"})
        assert r.status_code == 503 and "نصّك باقٍ في المحرر" in r.json()["error"]
