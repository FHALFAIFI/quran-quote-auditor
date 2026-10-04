"""The account API (roadmap Stage 2). Registered ONLY when ``ACCOUNTS_ENABLED`` is on (see ``install``); with the flag off
none of these routes exists and every /api/account/* path is a 404.

Rules kept by every handler:
- the user id is the verified token's ``sub`` (``Principal.user_id``); a user id in the body, the query or the path is
  never read;
- every draft lookup is scoped by that id; another user's draft, a deleted draft and a malformed id all answer 404, so the
  answer does not reveal whether an id exists;
- an update must name the version it was based on; a stale version is refused with 409 and both versions' metadata;
- limits (size of each field, number of drafts) are checked here with an Arabic message, and again by the database;
- logs carry the method, the route template, the draft id and the status code. Never a title, a body, decisions or a token.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .config import AccountConfig, service_role_key
from .store import AdminClient, AuthRejected, Conflict, DraftStore, LimitReached, NotFound, PostgrestStore, Unavailable
from .tokens import Denylist, JWKSCache, Principal, TokenError, TokenVerifier

log = logging.getLogger("auditor.accounts")

MAX_TOKEN_LIFETIME = 3600   # Supabase's default access-token lifetime; a deleted user's tokens are refused at least this long


def ar_num(n: int) -> str:
    return f"{n:,}".replace(",", "٬").translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


class AccountError(Exception):
    def __init__(self, status: int, code: str, message: str, extra: dict | None = None):
        super().__init__(code)
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}


NOT_FOUND = (404, "not_found", "لا توجد هذه المسودة في حسابك.")
SIGN_IN_AGAIN = (401, "auth", "انتهت جلسة الدخول أو لم تُقبل؛ سجّل الدخول من جديد. نصّك باقٍ في المحرر.")
UNAVAILABLE = (503, "unavailable", "تعذّر الوصول إلى خدمة الحسابات الآن؛ لم يُحفظ شيء. نصّك باقٍ في المحرر.")


@dataclass
class AccountsContext:
    cfg: AccountConfig
    verifier: TokenVerifier
    store: DraftStore
    admin: AdminClient
    rate_limited: Callable[[str], bool]
    client_ip: Callable[[Request], str]
    denylist: Denylist = field(default_factory=Denylist)


def _ctx(request: Request) -> AccountsContext:
    return request.app.state.accounts


def principal(request: Request) -> Principal:
    c = _ctx(request)
    if c.rate_limited(c.client_ip(request)):
        raise AccountError(429, "rate_limited", "طلبات كثيرة؛ انتظر دقيقة ثم أعد المحاولة. نصّك باقٍ في المحرر.")
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AccountError(*SIGN_IN_AGAIN)
    try:
        p = c.verifier.verify(token.strip())
    except TokenError:
        raise AccountError(*SIGN_IN_AGAIN) from None
    if c.denylist.refused(p):
        raise AccountError(*SIGN_IN_AGAIN)
    return p


def _draft_id(draft_id: str) -> str:
    try:
        return str(uuid.UUID(draft_id))
    except ValueError:
        raise AccountError(*NOT_FOUND) from None


# ---------------------------------------------------------------------------------------------------------------- models
class DraftCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")   # a user_id (or anything else) in the body is ignored, never used
    title: str = Field("", max_length=4000)
    body: str = Field(..., max_length=200_000)
    decisions: dict[str, Any] | list[Any] | None = None
    audited_text: str | None = Field(None, max_length=200_000)


class DraftUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    version: int = Field(..., ge=1, le=2**31)
    title: str | None = Field(None, max_length=4000)
    body: str | None = Field(None, max_length=200_000)
    decisions: dict[str, Any] | list[Any] | None = None
    audited_text: str | None = Field(None, max_length=200_000)


class PrefsIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    suggest_on: bool
    distinct_on: bool


def _check_limits(cfg: AccountConfig, fields: dict) -> None:
    if "title" in fields and len(fields["title"] or "") > cfg.max_title_chars:
        raise AccountError(400, "title_too_long", f"العنوان أطول من {ar_num(cfg.max_title_chars)} حرف؛ اختصره ثم احفظ.")
    for name in ("body", "audited_text"):
        if len(fields.get(name) or "") > cfg.max_body_chars:
            raise AccountError(413, "too_long", f"المسودة أطول من {ar_num(cfg.max_body_chars)} حرف، فلم تُحفظ في حسابك. نصّك باقٍ في المحرر.")
    if fields.get("decisions") is not None:
        size = len(json.dumps(fields["decisions"], ensure_ascii=False).encode())
        if size > cfg.max_decisions_bytes:
            raise AccountError(413, "decisions_too_large", "سجل القرارات أكبر من المسموح، فلم تُحفظ المسودة. نصّك باقٍ في المحرر.")


def _call(fn, *args):
    """Run a store call and turn its errors into answers. A refused token becomes 401; another user's row is 404."""
    try:
        return fn(*args)
    except NotFound:
        raise AccountError(*NOT_FOUND) from None
    except AuthRejected:
        raise AccountError(*SIGN_IN_AGAIN) from None
    except LimitReached:
        raise AccountError(400, "limit", "بلغت المسودة أو الحساب حدًّا مسموحًا به، فلم تُحفظ. نصّك باقٍ في المحرر.") from None
    except Unavailable:
        raise AccountError(*UNAVAILABLE) from None


def _public(d: dict) -> dict:
    out = {k: d.get(k) for k in ("id", "title", "body", "decisions", "audited_text", "created_at", "updated_at", "version")}
    out["length"] = d.get("body_length", len(d.get("body") or ""))
    return out


# ---------------------------------------------------------------------------------------------------------------- routes
router = APIRouter(prefix="/api/account")


@router.get("/config")
def account_config(request: Request):
    """What the browser needs to request a magic link: the project URL and the PUBLIC anon key. Nothing secret."""
    c = _ctx(request).cfg
    return {"supabase_url": c.supabase_url, "anon_key": c.anon_key, "max_drafts": c.max_drafts, "max_chars": c.max_body_chars}


@router.get("/drafts")
def list_drafts(request: Request, p: Principal = Depends(principal)):
    c = _ctx(request)
    return {"drafts": _call(c.store.list, p), "max_drafts": c.cfg.max_drafts}


@router.post("/drafts", status_code=201)
def create_draft(body: DraftCreate, request: Request, p: Principal = Depends(principal)):
    c = _ctx(request)
    fields = body.model_dump()
    _check_limits(c.cfg, fields)
    if _call(c.store.count, p) >= c.cfg.max_drafts:
        raise AccountError(400, "draft_limit", f"في حسابك {ar_num(c.cfg.max_drafts)} مسودة، وهو الحد الأقصى؛ احذف مسودة قديمة ثم احفظ. نصّك باقٍ في المحرر.")
    return _public(_call(c.store.create, p, fields))


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: str, request: Request, p: Principal = Depends(principal)):
    return _public(_call(_ctx(request).store.get, p, _draft_id(draft_id)))


@router.put("/drafts/{draft_id}")
def update_draft(draft_id: str, body: DraftUpdate, request: Request, p: Principal = Depends(principal)):
    c = _ctx(request)
    did = _draft_id(draft_id)
    fields = {k: v for k, v in body.model_dump(exclude={"version"}).items() if k in body.model_fields_set}
    if fields.get("body") is None:
        fields.pop("body", None)       # a body cannot be set to null; omit it to keep the stored one
    if fields.get("title") is None:
        fields.pop("title", None)
    _check_limits(c.cfg, fields)
    try:
        return _public(_call(c.store.update, p, did, body.version, fields))
    except Conflict as exc:
        mine = {"version": body.version, "length": len(fields["body"]) if "body" in fields else None, "title": fields.get("title")}
        raise AccountError(409, "conflict", "حُفظت هذه المسودة من مكان آخر بعد أن فتحتَها. اختر النسخة التي تبقى؛ لم يُكتب شيء فوق الأخرى.",
                           {"yours": mine, "saved": exc.current}) from None


@router.delete("/drafts/{draft_id}", status_code=204)
def delete_draft(draft_id: str, request: Request, p: Principal = Depends(principal)):
    _call(_ctx(request).store.delete, p, _draft_id(draft_id))
    return Response(status_code=204)


@router.get("/preferences")
def get_prefs(request: Request, p: Principal = Depends(principal)):
    return {"preferences": _call(_ctx(request).store.get_prefs, p)}


@router.put("/preferences")
def put_prefs(body: PrefsIn, request: Request, p: Principal = Depends(principal)):
    return {"preferences": _call(_ctx(request).store.put_prefs, p, body.model_dump())}


@router.get("/export")
def export_all(request: Request, p: Principal = Depends(principal)):
    c = _ctx(request)
    drafts = [_public(d) for d in _call(c.store.all, p)]
    return {"exported_at": datetime.now(timezone.utc).isoformat(),
            "note": "تصدير من مدقق الاقتباسات القرآنية: كل مسوداتك المحفوظة في حسابك وتفضيلاتك.",
            "preferences": _call(c.store.get_prefs, p), "drafts": drafts}


@router.post("/signout", status_code=204)
def sign_out(request: Request, p: Principal = Depends(principal)):
    """Refuse this token on this server from now on (the provider's sign-out ends the refresh token; this ends the access token here)."""
    c = _ctx(request)
    c.denylist.revoke_token(p, c.cfg.leeway)
    return Response(status_code=204)


@router.delete("")
def delete_account(request: Request, p: Principal = Depends(principal)):
    c = _ctx(request)
    n = _call(c.store.delete_all, p)
    key = service_role_key()
    auth_deleted = c.admin.delete_user(p.user_id, key) if key else False
    c.denylist.revoke_user(p.user_id, max(p.expires_at, time.time() + MAX_TOKEN_LIFETIME) + c.cfg.leeway)
    return {"deleted_drafts": n, "auth_user_deleted": auth_deleted}


# ---------------------------------------------------------------------------------------------------------------- install
def install(app: FastAPI, cfg: AccountConfig, rate_limited: Callable[[str], bool], client_ip: Callable[[Request], str]) -> AccountsContext:
    jwks = JWKSCache(cfg.jwks_url, cfg.jwks_ttl, cfg.jwks_min_refetch, timeout=cfg.timeout)
    ctx = AccountsContext(
        cfg=cfg,
        verifier=TokenVerifier(jwks, cfg.issuer, cfg.audience, cfg.leeway),
        store=PostgrestStore(cfg.supabase_url, cfg.anon_key, timeout=cfg.timeout),
        admin=AdminClient(cfg.supabase_url, timeout=cfg.timeout),
        rate_limited=rate_limited,
        client_ip=client_ip,
    )
    app.state.accounts = ctx

    @app.exception_handler(AccountError)
    async def account_error(request: Request, exc: AccountError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
        return JSONResponse({"error": exc.message, "code": exc.code, **exc.extra}, status_code=exc.status, headers=headers)

    @app.middleware("http")
    async def account_log(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/account"):
            route = request.scope.get("route")
            template = getattr(route, "path", "-")
            raw = request.scope.get("path_params", {}).get("draft_id")
            try:
                did = str(uuid.UUID(raw)) if raw else "-"
            except ValueError:
                did = "invalid"
            log.info("account %s %s id=%s status=%d", request.method, template, did, response.status_code)
        return response

    app.include_router(router)
    return ctx
