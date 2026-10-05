"""Configuration of the optional accounts feature (roadmap Stage 2), read from the environment.

The feature is OFF unless ``ACCOUNTS_ENABLED`` is ``true``. With it off, no account route is registered, the page loads no
account script, and the only visible trace is ``"accounts_enabled": false`` in ``/api/health``.

This module imports nothing beyond the standard library, so a server with the flag off never imports the JWT or store code.
The service-role key is read at call time (``service_role_key()``) and never kept on an object that could be serialised.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

log = logging.getLogger("auditor.accounts")

_TRUE = {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _origin(url: str) -> str | None:
    """scheme://host[:port] of a URL, or None when it is not an http(s) URL. HTTPS is required except on a loopback host
    (the local fake used by the tests)."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    if parts.scheme == "http" and parts.hostname not in ("127.0.0.1", "localhost", "::1"):
        return None
    return f"{parts.scheme}://{parts.netloc}"


@dataclass(frozen=True)
class AccountConfig:
    enabled: bool
    supabase_url: str = ""
    origin: str = ""            # for the CSP connect-src: the browser talks to Supabase Auth directly (magic link, sign-out)
    anon_key: str = ""          # public by design (the browser needs it); Row-Level Security is what protects the rows
    jwks_url: str = ""
    issuer: str = ""
    audience: str = "authenticated"
    leeway: float = 30.0        # seconds of clock skew allowed on exp / nbf / iat
    jwks_ttl: float = 600.0     # how long a fetched JWKS is trusted before it is fetched again
    jwks_min_refetch: float = 30.0   # an unknown kid triggers at most one refetch per this many seconds
    max_drafts: int = 200
    max_body_chars: int = 20000
    max_title_chars: int = 200
    max_decisions_bytes: int = 200_000
    rate_limit_per_minute: int = 60
    timeout: float = 8.0

    @classmethod
    def from_env(cls) -> "AccountConfig":
        if os.environ.get("ACCOUNTS_ENABLED", "").strip().lower() not in _TRUE:
            return cls(enabled=False)
        url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
        anon = os.environ.get("SUPABASE_ANON_KEY", "").strip()
        origin = _origin(url) if url else None
        if not origin or not anon:
            # Fail closed: a half-configured server behaves exactly as if the flag were off.
            log.warning("ACCOUNTS_ENABLED is set but SUPABASE_URL (https) or SUPABASE_ANON_KEY is missing; accounts stay off")
            return cls(enabled=False)
        jwks_url = os.environ.get("SUPABASE_JWKS_URL", "").strip() or f"{url}/auth/v1/.well-known/jwks.json"
        if not _origin(jwks_url):
            # The keys that decide who a writer is must not come over plain http (anyone on the path could swap them).
            log.warning("SUPABASE_JWKS_URL is not an https URL; accounts stay off")
            return cls(enabled=False)
        return cls(
            enabled=True,
            supabase_url=url,
            origin=origin,
            anon_key=anon,
            jwks_url=jwks_url,
            issuer=os.environ.get("SUPABASE_JWT_ISSUER", "").strip() or f"{url}/auth/v1",
            audience=os.environ.get("SUPABASE_JWT_AUDIENCE", "").strip() or "authenticated",
            leeway=max(0.0, min(_float("ACCOUNT_TOKEN_LEEWAY_SECONDS", 30.0), 120.0)),
            max_drafts=_int("ACCOUNT_MAX_DRAFTS", 200),
            max_body_chars=_int("ACCOUNT_MAX_DRAFT_CHARS", 20000),
            rate_limit_per_minute=_int("ACCOUNT_RATE_LIMIT_PER_MINUTE", 60),
        )


def service_role_key() -> str | None:
    """The Supabase service-role key, read at call time. Used ONLY by the server to delete the auth user after the writer
    asks to delete the account. It is never sent to the browser and never logged."""
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    return key or None
