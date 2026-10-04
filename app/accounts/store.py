"""Where account drafts live. Two implementations of one interface:

- ``PostgrestStore``: Supabase's PostgREST API over httpx. Every request carries the public anon key (``apikey``) and the
  WRITER'S OWN access token (``Authorization: Bearer``), so Postgres Row-Level Security sees the same user the server
  verified and acts as a second guard. The service-role key is never used here. Every query is also filtered by the
  verified user id, so isolation does not rest on RLS alone.
- ``MemoryStore``: for tests only. It enforces per-user isolation itself, so the API's isolation is tested independently
  of any database policy.

Neither logs draft text, titles or tokens.
"""

from __future__ import annotations

import copy
import hashlib
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from .tokens import Principal

DRAFT_FIELDS = ("title", "body", "decisions", "audited_text")
META_COLUMNS = "id,title,created_at,updated_at,version,body_length"
FULL_COLUMNS = "id,title,body,decisions,audited_text,created_at,updated_at,version,body_length"


class StoreError(Exception):
    """Base class. Messages are machine reasons, never content."""


class NotFound(StoreError):
    pass


class Conflict(StoreError):
    def __init__(self, current: dict):
        super().__init__("version conflict")
        self.current = current   # the stored draft's metadata (no body)


class LimitReached(StoreError):
    pass


class AuthRejected(StoreError):
    """The store refused the token (expired or revoked at the provider)."""


class Unavailable(StoreError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def meta_of(d: dict) -> dict:
    return {"id": d["id"], "title": d.get("title") or "", "created_at": d.get("created_at"), "updated_at": d.get("updated_at"),
            "version": d.get("version"), "length": d.get("body_length", len(d.get("body") or ""))}


class DraftStore(Protocol):
    def list(self, p: Principal) -> list[dict]: ...
    def all(self, p: Principal) -> list[dict]: ...
    def count(self, p: Principal) -> int: ...
    def create(self, p: Principal, fields: dict) -> dict: ...
    def get(self, p: Principal, draft_id: str) -> dict: ...
    def update(self, p: Principal, draft_id: str, version: int, fields: dict) -> dict: ...
    def delete(self, p: Principal, draft_id: str) -> None: ...
    def get_prefs(self, p: Principal) -> dict | None: ...
    def put_prefs(self, p: Principal, prefs: dict) -> dict: ...
    def delete_all(self, p: Principal) -> int: ...


# ----------------------------------------------------------------------------------------------------------- memory (tests)
class MemoryStore:
    """In-memory store for tests. Rows are keyed by (user_id, draft_id): a lookup with another user's id cannot reach a row."""

    def __init__(self, max_drafts: int = 200):
        self.max_drafts = max_drafts
        self._drafts: dict[str, dict[str, dict]] = {}
        self._prefs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _mine(self, p: Principal) -> dict[str, dict]:
        return self._drafts.setdefault(p.user_id, {})

    def list(self, p):
        with self._lock:
            rows = sorted(self._mine(p).values(), key=lambda d: d["updated_at"], reverse=True)
            return [meta_of(d) for d in rows]

    def all(self, p):
        with self._lock:
            rows = sorted(self._mine(p).values(), key=lambda d: d["updated_at"], reverse=True)
            return [self._public(d) for d in rows]

    def count(self, p):
        with self._lock:
            return len(self._mine(p))

    def create(self, p, fields):
        with self._lock:
            mine = self._mine(p)
            if len(mine) >= self.max_drafts:   # the same rule as the SQL trigger
                raise LimitReached("draft count")
            now = _now()
            d = {"id": str(uuid.uuid4()), "user_id": p.user_id, "title": "", "body": "", "decisions": None, "audited_text": None,
                 **{k: copy.deepcopy(v) for k, v in fields.items() if k in DRAFT_FIELDS}, "created_at": now, "updated_at": now, "version": 1}
            d["body_length"] = len(d["body"] or "")
            mine[d["id"]] = d
            return self._public(d)

    @staticmethod
    def _public(d):
        out = {k: copy.deepcopy(v) for k, v in d.items() if k != "user_id"}
        return out

    def get(self, p, draft_id):
        with self._lock:
            d = self._mine(p).get(draft_id)
            if d is None:
                raise NotFound("draft")
            return self._public(d)

    def update(self, p, draft_id, version, fields):
        with self._lock:
            d = self._mine(p).get(draft_id)
            if d is None:
                raise NotFound("draft")
            if d["version"] != version:
                raise Conflict(meta_of(d))
            for k, v in fields.items():
                if k in DRAFT_FIELDS:
                    d[k] = copy.deepcopy(v)
            d["body_length"] = len(d["body"] or "")
            d["version"] += 1
            d["updated_at"] = _now()
            return self._public(d)

    def delete(self, p, draft_id):
        with self._lock:
            if self._mine(p).pop(draft_id, None) is None:
                raise NotFound("draft")

    def get_prefs(self, p):
        with self._lock:
            got = self._prefs.get(p.user_id)
            return dict(got) if got else None

    def put_prefs(self, p, prefs):
        with self._lock:
            row = {"suggest_on": bool(prefs["suggest_on"]), "distinct_on": bool(prefs["distinct_on"]), "updated_at": _now()}
            self._prefs[p.user_id] = row
            return dict(row)

    def delete_all(self, p):
        with self._lock:
            n = len(self._drafts.pop(p.user_id, {}))
            self._prefs.pop(p.user_id, None)
            return n


# ------------------------------------------------------------------------------------------------------------- PostgREST
class PostgrestStore:
    def __init__(self, supabase_url: str, anon_key: str, client: httpx.Client | None = None, timeout: float = 8.0):
        self.base = supabase_url.rstrip("/") + "/rest/v1"
        self.anon_key = anon_key
        self.client = client or httpx.Client(timeout=timeout)

    def _headers(self, p: Principal, prefer: str | None = None) -> dict:
        # The writer's own token: RLS applies to this user. Never the service-role key.
        h = {"apikey": self.anon_key, "Authorization": f"Bearer {p.token}", "Accept": "application/json"}
        if prefer:
            h["Prefer"] = prefer
        return h

    def _call(self, method: str, path: str, p: Principal, params: dict | None = None, json: Any = None, prefer: str | None = None):
        try:
            res = self.client.request(method, self.base + path, params=params, json=json, headers=self._headers(p, prefer))
        except httpx.HTTPError as exc:
            raise Unavailable(type(exc).__name__) from None
        if res.status_code < 300:
            return res.json() if res.content else None
        self._raise(res)

    @staticmethod
    def _raise(res: httpx.Response):
        try:
            err = res.json()
            code, message = str(err.get("code") or ""), str(err.get("message") or "")
        except ValueError:
            code, message = "", ""
        if res.status_code == 401 or code.startswith("PGRST30"):    # PGRST301/302/303: JWT invalid, missing or expired
            raise AuthRejected(code or "401")
        if code == "23514" or message == "draft_limit":             # check_violation: body too long, or the count trigger
            raise LimitReached(code or "limit")
        if code == "42501" or res.status_code == 403:               # RLS refused: answered as not found, never as forbidden
            raise NotFound(code or "403")
        if res.status_code == 404 or code == "PGRST116":
            raise NotFound(code or "404")
        if code == "22P02":                                         # invalid uuid text
            raise NotFound(code)
        raise Unavailable(f"{res.status_code} {code}")

    @staticmethod
    def _one(rows) -> dict:
        if not rows:
            raise NotFound("draft")
        return rows[0]

    def list(self, p):
        rows = self._call("GET", "/drafts", p, params={"select": META_COLUMNS, "user_id": f"eq.{p.user_id}", "order": "updated_at.desc"})
        return [meta_of(r) for r in rows or []]

    def all(self, p):
        return self._call("GET", "/drafts", p, params={"select": FULL_COLUMNS, "user_id": f"eq.{p.user_id}", "order": "updated_at.desc"}) or []

    def count(self, p):
        return len(self._call("GET", "/drafts", p, params={"select": "id", "user_id": f"eq.{p.user_id}"}) or [])

    def create(self, p, fields):
        row = {k: v for k, v in fields.items() if k in DRAFT_FIELDS}
        row["user_id"] = p.user_id   # the verified id; the column default auth.uid() and the RLS check give the same value
        return self._one(self._call("POST", "/drafts", p, params={"select": FULL_COLUMNS}, json=row, prefer="return=representation"))

    def get(self, p, draft_id):
        return self._one(self._call("GET", "/drafts", p, params={"select": FULL_COLUMNS, "id": f"eq.{draft_id}", "user_id": f"eq.{p.user_id}"}))

    def update(self, p, draft_id, version, fields):
        row = {k: v for k, v in fields.items() if k in DRAFT_FIELDS}
        # The version filter makes the update conditional; the trigger bumps version and updated_at.
        rows = self._call("PATCH", "/drafts", p, json=row, prefer="return=representation",
                          params={"select": FULL_COLUMNS, "id": f"eq.{draft_id}", "user_id": f"eq.{p.user_id}", "version": f"eq.{int(version)}"})
        if rows:
            return rows[0]
        current = self._call("GET", "/drafts", p, params={"select": META_COLUMNS, "id": f"eq.{draft_id}", "user_id": f"eq.{p.user_id}"})
        if not current:
            raise NotFound("draft")
        raise Conflict(meta_of(current[0]))

    def delete(self, p, draft_id):
        rows = self._call("DELETE", "/drafts", p, params={"select": "id", "id": f"eq.{draft_id}", "user_id": f"eq.{p.user_id}"},
                          prefer="return=representation")
        if not rows:
            raise NotFound("draft")

    def get_prefs(self, p):
        rows = self._call("GET", "/preferences", p, params={"select": "suggest_on,distinct_on,updated_at", "user_id": f"eq.{p.user_id}"})
        return rows[0] if rows else None

    def put_prefs(self, p, prefs):
        row = {"user_id": p.user_id, "suggest_on": bool(prefs["suggest_on"]), "distinct_on": bool(prefs["distinct_on"])}
        rows = self._call("POST", "/preferences", p, params={"on_conflict": "user_id", "select": "suggest_on,distinct_on,updated_at"},
                          json=row, prefer="resolution=merge-duplicates,return=representation")
        return self._one(rows)

    def delete_all(self, p):
        rows = self._call("DELETE", "/drafts", p, params={"select": "id", "user_id": f"eq.{p.user_id}"}, prefer="return=representation")
        self._call("DELETE", "/preferences", p, params={"user_id": f"eq.{p.user_id}"})
        return len(rows or [])


@dataclass
class AdminClient:
    """The one place the service-role key is used: deleting the auth user after the writer deleted the account, and writing
    a content-free line to deletion_log. Server-side only; the key is read at call time and never logged or returned."""

    supabase_url: str
    client: httpx.Client | None = None
    timeout: float = 8.0

    def delete_user(self, user_id: str, service_key: str) -> bool:
        c = self.client or httpx.Client(timeout=self.timeout)
        h = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        requested = _now()
        try:
            res = c.delete(f"{self.supabase_url}/auth/v1/admin/users/{uuid.UUID(user_id)}", headers=h)
            ok = res.status_code in (200, 204, 404)
            c.post(f"{self.supabase_url}/rest/v1/deletion_log", headers={**h, "Prefer": "return=minimal"},
                   json={"user_hash": hashlib.sha256(user_id.encode()).hexdigest(), "requested_at": requested,
                         "completed_at": _now() if ok else None})
            return ok
        except httpx.HTTPError:
            return False
