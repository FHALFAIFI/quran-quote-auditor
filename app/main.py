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
from pydantic import BaseModel, ConfigDict, Field

from .audit import InputError, run_audit, run_phrase
from .config import settings
from .extraction import get_provider
from .quran_source import SourceUnavailable, source
from .suggest import MAX_AFTER, MAX_BEFORE, suggest as suggest_verses

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("auditor")
logging.getLogger("httpx").setLevel(logging.WARNING)  # request URLs are noise; bodies are never logged

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
async def security_headers(request: Request, call_next):
    if request.method == "POST":
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse({"error": "حجم الطلب أكبر من المسموح."}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # Log only the exception type — never the request body.
    log.error("unhandled error on %s: %s", request.url.path, type(exc).__name__)
    return JSONResponse({"error": "حدث خطأ غير متوقع أثناء التدقيق."}, status_code=500)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse({"error": "صيغة الطلب غير صحيحة أو النص أطول من المسموح."}, status_code=422)


@app.get("/api/health")
def health():
    provider = get_provider()
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
        "source": source.status(),
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
