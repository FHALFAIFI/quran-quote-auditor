"""FastAPI application: JSON API + static Arabic frontend.

Privacy: submitted articles are processed in memory only. They are never
written to disk, stored, or logged; error handlers return generic messages.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders
from pydantic import BaseModel, ConfigDict, Field

from .audit import InputError, run_audit, run_phrase
from . import logging_safety
from .config import settings
from .extraction import get_provider
from .quran_source import SourceUnavailable, source
from .suggest import MAX_AFTER, MAX_BEFORE, suggest as suggest_verses

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("auditor")
logging.getLogger("httpx").setLevel(logging.WARNING)  # request URLs are noise; bodies are never logged
logging_safety.install()  # defence in depth: a long run of Arabic text never reaches a log line (app/logging_safety.py)

STATIC = Path(__file__).parent / "static"
MAX_BODY_BYTES = settings.max_chars * 4 + 1024  # UTF-8 Arabic ≈ 2 bytes/char; generous margin

app = FastAPI(title="مدقق الاقتباسات القرآنية", docs_url=None, redoc_url=None, openapi_url=None)


class AuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    article: str = Field(..., max_length=settings.max_chars * 2)
    ai: Literal[True] = True  # accept an older cached page's ai:true; ai:false cannot disable the model


class SuggestRequest(BaseModel):
    """The words before (and after) the caret, and why the browser asks: the writer pressed «أكمل من المصحف» (explicit) or chose
    suggestions without a lead-in (distinct). No article is sent, only this window of text; it is not stored or logged."""

    before: str = Field(..., max_length=MAX_BEFORE)   # offsets in the answer refer to this string: more is refused, not cut
    after: str = Field("", max_length=MAX_AFTER)
    explicit: bool = False
    distinct: bool = False
    request_id: int | None = Field(None, ge=0, le=2**31)


class PhraseRequest(BaseModel):
    """A span the editor highlighted (code-point offsets into ``article``) and, optionally, the verse they chose."""

    article: str = Field(..., max_length=settings.max_chars * 2)
    start: int
    end: int
    surah: int | None = Field(None, ge=1, le=114)
    ayah_start: int | None = Field(None, ge=1, le=286)
    ayah_end: int | None = Field(None, ge=1, le=286)
    finding_id: int = Field(1, ge=1, le=10_000)
    # spans (start, end) of the other findings the browser shows, so a reference they own is not taken by this span
    others: list[tuple[int, int]] = Field(default_factory=list, max_length=200)


# --- tiny in-memory rate limiter (per instance, best effort) ---------------
# Two buckets: audits / phrase checks (each can be slow and may call the model) and verse suggestions (a lookup of about a millisecond,
# asked for while the writer types, so a much higher allowance).
_hits: dict[tuple[str, str], deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def _rate_limited(ip: str, bucket: str = "audit") -> bool:
    limit = settings.rate_limit_per_minute if bucket == "audit" else settings.suggest_rate_limit_per_minute
    now = time.monotonic()
    with _hits_lock:
        q = _hits[(bucket, ip)]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            return True
        q.append(now)
        if len(_hits) > 5000:  # bound memory: first the keys with no recent request, then (a flood of distinct addresses) the oldest keys
            for k in [k for k, v in _hits.items() if not v][:1000]:
                _hits.pop(k, None)
            if len(_hits) > 5000:
                for k in list(_hits)[:1000]:
                    _hits.pop(k, None)
        return False


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")


@app.middleware("http")
async def answer_unexpected_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:  # noqa: BLE001
        # Answered here rather than by the Exception handler below: Starlette re-raises after that handler so the server can log
        # it, and uvicorn then writes the full traceback, whose message can quote the article. Here only the type is logged.
        return _unexpected(request, exc)


# --- security headers and a hard cap on the request body (pure ASGI, so it covers the API, the pages and /static) --------
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; worker-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": CSP,
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}
HSTS = "max-age=31536000"
TOO_LARGE = {"error": "حجم الطلب أكبر من المسموح."}


def _is_https(scope) -> bool:
    if scope.get("scheme") == "https":
        return True
    for k, v in scope.get("headers") or ():
        if k == b"x-forwarded-proto":  # set by Render's proxy; HSTS is ignored by browsers over plain http anyway
            return v.split(b",")[0].strip().lower() == b"https"
    return False


class SecurityMiddleware:
    """Adds the security headers to every response and refuses a request body over ``max_body`` bytes with 413.

    The body is counted as it arrives, so a chunked request without Content-Length cannot get past the cap. Requests with
    a body are buffered here (at most ``max_body`` bytes) and replayed to the app."""

    def __init__(self, app, max_body: int) -> None:
        self.app = app
        self.max_body = max_body

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        https = _is_https(scope)
        api = scope.get("path", "").startswith("/api/")

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for k, v in SECURITY_HEADERS.items():
                    headers[k] = v
                if https:
                    headers["Strict-Transport-Security"] = HSTS
                if api:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        if scope.get("method") in ("POST", "PUT", "PATCH", "DELETE"):
            length = None
            for k, v in scope.get("headers") or ():
                if k == b"content-length":
                    length = v
            if length is not None and length.isdigit() and int(length) > self.max_body:
                return await JSONResponse(TOO_LARGE, status_code=413)(scope, receive, send_with_headers)
            chunks, size = [], 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body = message.get("body", b"")
                size += len(body)
                if size > self.max_body:
                    return await JSONResponse(TOO_LARGE, status_code=413)(scope, receive, send_with_headers)
                chunks.append(body)
                if not message.get("more_body", False):
                    break
            buffered = {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            replayed = False

            async def replay():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return buffered
                return await receive()

            return await self.app(scope, replay, send_with_headers)
        return await self.app(scope, receive, send_with_headers)


# added last, so it is the outermost layer: its headers also reach the 500 answer of the guard above
app.add_middleware(SecurityMiddleware, max_body=MAX_BODY_BYTES)


def _unexpected(request: Request, exc: Exception) -> JSONResponse:
    # Log only the exception type — never the request body, the exception message or a traceback (either may quote the article).
    log.error("unhandled error on %s: %s", request.url.path, type(exc).__name__)
    # This answer is sent by the outermost error middleware, outside SecurityMiddleware: add the headers here.
    return JSONResponse({"error": "حدث خطأ غير متوقع أثناء التدقيق."}, status_code=500,
                        headers={**SECURITY_HEADERS, "Cache-Control": "no-store"})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    return _unexpected(request, exc)  # reached only by an error outside the middleware above


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse({"error": "صيغة الطلب غير صحيحة أو النص أطول من المسموح."}, status_code=422)


@app.get("/api/health")
def health(deep: bool = False):
    """Public, no personal data. ``?deep=1`` (for an external uptime monitor) first makes sure the Quran text is loaded: at
    most one Quranpedia request per 24 h or per failure back-off, exactly as an audit would. Without it nothing is fetched."""
    provider = get_provider()
    if deep:
        try:
            source.get()
        except SourceUnavailable:
            pass
    src = source.status()
    return {
        "status": "ok",
        # "ai" means a provider is CONFIGURED (a key is set). Whether it has actually
        # answered on this server instance is in "ai_last_call" (never_called | ok | failed).
        "mode": "ai" if provider else "reduced",
        "ai_configured": provider is not None,
        "provider": provider.label if provider else None,
        "provider_name": provider.name if provider else None,
        "ai_selection": settings.ai_provider,
        "ai_last_call": provider.tracker.status() if provider and provider.tracker else None,
        "max_chars": settings.max_chars,
        "ai_max_chars": settings.ai_max_chars,
        # The commit the host built (Render sets RENDER_GIT_COMMIT; public information, null elsewhere).
        "build": (os.environ.get("RENDER_GIT_COMMIT") or "")[:40] or None,
        "source": src,
        # For monitors: the Quran text is loaded and not a stale fallback copy (false before the first load: use ?deep=1).
        "source_ok": bool(src.get("loaded") and not src.get("stale")),
        # Model calls since this process started (counts only; null when no model is configured).
        "ai_recent": provider.tracker.recent() if provider and provider.tracker else None,
    }


@app.post("/api/audit")
def audit(body: AuditRequest, request: Request):
    if _rate_limited(_client_ip(request)):
        return JSONResponse({"error": "عدد الطلبات كبير؛ حاول بعد دقيقة."}, status_code=429)
    try:
        return run_audit(body.article)
    except InputError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/phrase")
def phrase(body: PhraseRequest, request: Request):
    """Verify one highlighted span without AI (no Groq call): the manual path for phrases the search missed."""
    if _rate_limited(_client_ip(request)):
        return JSONResponse({"error": "عدد الطلبات كبير؛ حاول بعد دقيقة."}, status_code=429)
    try:
        return run_phrase(body.article, body.start, body.end, body.surah, body.ayah_start, body.ayah_end, body.finding_id, body.others)
    except InputError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except SourceUnavailable:
        return JSONResponse({"error": "تعذّر الوصول إلى قرآنبيديا الآن. أعد المحاولة لاحقًا."}, status_code=503)


@app.post("/api/suggest")
def suggest(body: SuggestRequest, request: Request):
    """Verse suggestions for the caret at the end of ``before``: looked up in the Quranpedia text, no model, nothing stored."""
    if _rate_limited(_client_ip(request), "suggest"):
        return JSONResponse({"error": "عدد الطلبات كبير؛ حاول بعد لحظات."}, status_code=429)
    try:
        index = source.get()
    except SourceUnavailable:
        return {"request_id": body.request_id, "status": "none", "reason": "source_unavailable", "trigger": None, "choices": [],
                "ambiguous": False, "places": 0}
    result = suggest_verses(index, body.before, body.after, explicit=body.explicit, distinct=body.distinct)
    result["request_id"] = body.request_id
    result["stale_source"] = bool(index.stale)
    return result


# The trust pages are separate documents: what the sources are, what happens to a draft, what the tool cannot do.
PAGES = {"sources": "sources.html", "privacy": "privacy.html", "limitations": "limitations.html"}


def _page(name: str):
    return FileResponse(STATIC / PAGES[name], headers={"Cache-Control": "no-cache"})


@app.get("/sources")
def sources_page():
    return _page("sources")


@app.get("/privacy")
def privacy_page():
    return _page("privacy")


@app.get("/limitations")
def limitations_page():
    return _page("limitations")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC), name="static")
