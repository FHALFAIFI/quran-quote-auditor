"""FastAPI application: JSON API + static Arabic frontend.

Privacy: submitted articles are processed in memory only. They are never
written to disk, stored, or logged; error handlers return generic messages.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .audit import InputError, run_audit
from .config import settings
from .extraction import get_provider
from .quran_source import source

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("auditor")
logging.getLogger("httpx").setLevel(logging.WARNING)  # request URLs are noise; bodies are never logged

STATIC = Path(__file__).parent / "static"
MAX_BODY_BYTES = settings.max_chars * 4 + 1024  # UTF-8 Arabic ≈ 2 bytes/char; generous margin

app = FastAPI(title="مدقق الاقتباسات القرآنية", docs_url=None, redoc_url=None, openapi_url=None)


class AuditRequest(BaseModel):
    article: str = Field(..., max_length=settings.max_chars * 2)


# --- tiny in-memory rate limiter (per instance, best effort) ---------------
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    with _hits_lock:
        q = _hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= settings.rate_limit_per_minute:
            return True
        q.append(now)
        if len(_hits) > 5000:  # bound memory
            for k in [k for k, v in _hits.items() if not v][:1000]:
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
        "mode": "ai" if provider else "reduced",
        "provider": provider.label if provider else None,
        "max_chars": settings.max_chars,
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


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC), name="static")
