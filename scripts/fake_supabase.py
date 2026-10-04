"""A LOCAL FAKE of Supabase Auth + PostgREST, for scripts/ui_account_e2e.mjs only. NOT the real service.

It listens on 127.0.0.1 and imitates just enough of the two APIs the app uses:

- Auth: the JWKS (one ES256 key generated at start), POST /auth/v1/otp (records a magic link instead of sending email),
  GET /auth/v1/verify (redirects to redirect_to#access_token=… like the real implicit flow), POST /auth/v1/logout, and
  DELETE /auth/v1/admin/users/{id} (service-role key only).
- PostgREST: /rest/v1/drafts, /rest/v1/preferences, /rest/v1/deletion_log with the eq. filters, Prefer headers and error
  codes PostgrestStore uses. Row-Level Security is IMITATED (rows filtered by the token's sub, inserts checked) — this is a
  Python imitation of the policies in deploy/supabase/001_drafts.sql, not Postgres, so it proves nothing about the SQL.
- Test controls under /__fake/: the last magic link for an address, the lifetime of the next tokens, the request log and
  a row count per user.

Usage: python scripts/fake_supabase.py [--port 0] [--anon KEY] [--service KEY]   (prints "READY <port>" when listening)
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, quote, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

LOCK = threading.Lock()
STATE = {"users": {}, "links": {}, "drafts": {}, "prefs": {}, "deletion_log": [], "requests": [], "ttl": 3600, "logouts": []}
KEY = ec.generate_private_key(ec.SECP256R1())
JWK = {**json.loads(jwt.algorithms.ECAlgorithm.to_jwk(KEY.public_key())), "kid": "fake-es256-1", "alg": "ES256", "use": "sig"}
ARGS = None
BASE = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mint(user_id: str, email: str) -> tuple[str, int]:
    now = int(time.time())
    exp = now + int(STATE["ttl"])
    claims = {"sub": user_id, "aud": "authenticated", "iss": f"{BASE}/auth/v1", "iat": now, "exp": exp, "role": "authenticated",
              "email": email, "session_id": str(uuid.uuid4())}
    return jwt.encode(claims, KEY, algorithm="ES256", headers={"kid": JWK["kid"]}), exp


class Handler(BaseHTTPRequestHandler):
    server_version = "fake-supabase/0"

    def log_message(self, *a):  # quiet
        pass

    # ------------------------------------------------------------------ plumbing
    def _cors(self):
        origin = self.headers.get("Origin")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _send(self, status: int, body=None, headers: dict | None = None):
        data = b"" if body is None else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self._cors()
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        if body is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        return json.loads(raw) if raw else None

    def _who(self):
        """(kind, sub): kind is service | user | anon | none | expired | bad, from the apikey and Authorization headers."""
        apikey = self.headers.get("apikey", "")
        auth = self.headers.get("Authorization", "")
        bearer = auth[7:] if auth.lower().startswith("bearer ") else ""
        if apikey == ARGS.service and bearer == ARGS.service:
            return "service", None
        if apikey not in (ARGS.anon, ARGS.service):
            return "none", None
        if not bearer or bearer == ARGS.anon:
            return "anon", None
        try:
            c = jwt.decode(bearer, KEY.public_key(), algorithms=["ES256"], audience="authenticated", issuer=f"{BASE}/auth/v1")
        except jwt.ExpiredSignatureError:
            return "expired", None
        except jwt.InvalidTokenError:
            return "bad", None
        return "user", c["sub"]

    def _record(self, kind):
        with LOCK:
            STATE["requests"].append({"method": self.command, "path": urlsplit(self.path).path, "auth": kind,
                                      "origin": self.headers.get("Origin"), "t": time.time()})

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Headers", "apikey, authorization, content-type, prefer, x-client-info")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self): self._route()
    def do_POST(self): self._route()
    def do_PATCH(self): self._route()
    def do_DELETE(self): self._route()

    def _route(self):
        parts = urlsplit(self.path)
        path, q = parts.path, dict(parse_qsl(parts.query, keep_blank_values=True))
        if path.startswith("/__fake/"):
            return self._control(path, q)
        kind, sub = self._who()
        self._record(kind)
        if path.startswith("/auth/v1/"):
            return self._auth(path[len("/auth/v1"):], q, kind, sub)
        if path.startswith("/rest/v1/"):
            return self._rest(path[len("/rest/v1/"):], q, kind, sub)
        self._send(404, {"message": "not found"})

    # ------------------------------------------------------------------ test controls
    def _control(self, path, q):
        if path == "/__fake/link":
            with LOCK:
                links = [(t, l) for t, l in STATE["links"].items() if l["email"] == q.get("email")]
            if not links:
                return self._send(404, {"error": "no link"})
            tok, link = links[-1]
            url = f"{BASE}/auth/v1/verify?token={tok}&type=magiclink&redirect_to={quote(link['redirect_to'], safe='')}"
            return self._send(200, {"link": url, "redirect_to": link["redirect_to"]})
        if path == "/__fake/ttl" and self.command == "POST":
            STATE["ttl"] = int((self._body() or {}).get("seconds", 3600))
            return self._send(200, {"ttl": STATE["ttl"]})
        if path == "/__fake/requests":
            with LOCK:
                return self._send(200, {"requests": STATE["requests"], "logouts": STATE["logouts"]})
        if path == "/__fake/state":
            with LOCK:
                counts = {u: len(d) for u, d in STATE["drafts"].items() if d}
                return self._send(200, {"users": {e: u for e, u in STATE["users"].items()}, "drafts": counts,
                                        "prefs": list(STATE["prefs"]), "deletion_log": STATE["deletion_log"]})
        self._send(404, {"error": "unknown control"})

    # ------------------------------------------------------------------ auth
    def _auth(self, path, q, kind, sub):
        if path == "/.well-known/jwks.json":
            return self._send(200, {"keys": [JWK]})
        if path == "/otp" and self.command == "POST":
            if kind == "none":
                return self._send(401, {"message": "Invalid API key"})
            body = self._body() or {}
            email = str(body.get("email", "")).strip().lower()
            redirect = q.get("redirect_to", "")
            if "@" not in email or not redirect.startswith(ARGS.allow_redirect):
                return self._send(400, {"message": "bad request"})
            with LOCK:
                STATE["users"].setdefault(email, str(uuid.uuid4()))
                STATE["links"][secrets.token_urlsafe(16)] = {"email": email, "redirect_to": redirect, "used": False, "at": time.time()}
            return self._send(200, {})
        if path == "/verify" and self.command == "GET":
            with LOCK:
                link = STATE["links"].get(q.get("token", ""))
                ok = bool(link) and not link["used"] and link["email"] in STATE["users"]
                if ok:
                    link["used"] = True
                    uid = STATE["users"][link["email"]]
            redirect = q.get("redirect_to") or (link or {}).get("redirect_to") or "/"
            if not ok:
                return self._send(303, None, {"Location": f"{redirect}#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired"})
            tok, exp = mint(uid, link["email"])
            frag = f"access_token={tok}&expires_at={exp}&expires_in={exp - int(time.time())}&refresh_token={secrets.token_urlsafe(12)}&token_type=bearer&type=magiclink"
            return self._send(303, None, {"Location": f"{redirect}#{frag}"})
        if path == "/logout" and self.command == "POST":
            with LOCK:
                STATE["logouts"].append({"scope": q.get("scope", "global"), "auth": kind})
            return self._send(204)
        if path.startswith("/admin/users/") and self.command == "DELETE":
            if kind != "service":
                return self._send(403, {"message": "service role required"})
            uid = path.rsplit("/", 1)[1]
            with LOCK:
                for e, u in list(STATE["users"].items()):
                    if u == uid:
                        del STATE["users"][e]
                        for t, l in STATE["links"].items():
                            if l["email"] == e:
                                l["used"] = True
                STATE["drafts"].pop(uid, None)    # on delete cascade
                STATE["prefs"].pop(uid, None)
            return self._send(200, {})
        self._send(404, {"message": "not found"})

    # ------------------------------------------------------------------ PostgREST imitation
    def _rest(self, table, q, kind, sub):
        if kind == "expired":
            return self._send(401, {"code": "PGRST303", "message": "JWT expired"})
        if kind in ("none", "bad"):
            return self._send(401, {"code": "PGRST301", "message": "JWT invalid"})
        prefer = self.headers.get("Prefer", "")
        want = "return=representation" in prefer
        filters = {k: v[3:] for k, v in q.items() if v.startswith("eq.")}
        cols = [c for c in q.get("select", "").split(",") if c]
        project = (lambda r: {c: r.get(c) for c in cols}) if cols else (lambda r: dict(r))
        if table == "deletion_log":
            if kind != "service" or self.command != "POST":
                return self._send(403, {"code": "42501", "message": "permission denied"})
            with LOCK:
                STATE["deletion_log"].append(self._body())
            return self._send(201)
        if kind != "user":   # the anon role has no grant on drafts or preferences
            return self._send(401 if kind == "anon" else 403, {"code": "42501", "message": "permission denied for table"})
        if table == "drafts":
            return self._drafts(sub, filters, project, want)
        if table == "preferences":
            return self._prefs(sub, filters, project, q)
        self._send(404, {"code": "PGRST205", "message": "table not found"})

    @staticmethod
    def _match(row, filters):
        return all(str(row.get(k)) == v for k, v in filters.items())

    def _drafts(self, sub, filters, project, want):
        with LOCK:
            mine = STATE["drafts"].setdefault(sub, {})   # RLS imitation: only the caller's rows are visible at all
            if self.command == "GET":
                rows = sorted((r for r in mine.values() if self._match(r, filters)), key=lambda r: r["updated_at"], reverse=True)
                return self._send(200, [project(r) for r in rows])
            if self.command == "POST":
                body = self._body() or {}
                if body.get("user_id", sub) != sub:
                    return self._send(403, {"code": "42501", "message": "new row violates row-level security policy"})
                if len(body.get("body") or "") > 20000 or len(body.get("title") or "") > 200:
                    return self._send(400, {"code": "23514", "message": "new row violates check constraint"})
                if len(mine) >= 200:
                    return self._send(400, {"code": "23514", "message": "draft_limit"})
                t = now_iso()
                row = {"title": "", "body": "", "decisions": None, "audited_text": None, **{k: body.get(k) for k in ("title", "body", "decisions", "audited_text") if k in body},
                       "id": str(uuid.uuid4()), "user_id": sub, "created_at": t, "updated_at": t, "version": 1}
                row["body_length"] = len(row["body"] or "")
                mine[row["id"]] = row
                return self._send(201, [project(row)] if want else None)
            if self.command == "PATCH":
                body = self._body() or {}
                out = []
                for r in mine.values():
                    if self._match(r, filters):
                        for k in ("title", "body", "decisions", "audited_text"):
                            if k in body:
                                r[k] = body[k]
                        r["body_length"] = len(r["body"] or "")
                        r["version"] += 1
                        r["updated_at"] = now_iso()
                        out.append(project(r))
                return self._send(200, out if want else None)
            if self.command == "DELETE":
                gone = [r for r in mine.values() if self._match(r, filters)]
                for r in gone:
                    del mine[r["id"]]
                return self._send(200, [project(r) for r in gone] if want else None)
        self._send(405, {"message": "method"})

    def _prefs(self, sub, filters, project, q):
        with LOCK:
            if self.command == "GET":
                row = STATE["prefs"].get(sub)
                return self._send(200, [project(row)] if row and self._match({**row, "user_id": sub}, filters) else [])
            if self.command == "POST":
                body = self._body() or {}
                if body.get("user_id", sub) != sub:
                    return self._send(403, {"code": "42501", "message": "new row violates row-level security policy"})
                row = {"suggest_on": bool(body.get("suggest_on", True)), "distinct_on": bool(body.get("distinct_on", False)), "updated_at": now_iso()}
                STATE["prefs"][sub] = row
                return self._send(201, [project(row)])
            if self.command == "DELETE":
                STATE["prefs"].pop(sub, None)
                return self._send(204)
        self._send(405, {"message": "method"})


def main():
    global ARGS, BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--anon", default="fake-anon-key")
    ap.add_argument("--service", default="fake-service-role-key")
    ap.add_argument("--allow-redirect", default="http://127.0.0.1:")
    ARGS = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", ARGS.port), Handler)
    BASE = f"http://127.0.0.1:{srv.server_address[1]}"
    print(f"READY {srv.server_address[1]}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
