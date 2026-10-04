"""Verification of the access token the browser sends (a Supabase Auth JWT). The server trusts nothing the browser says
about who it is: the user id is the ``sub`` claim of a token whose signature, issuer, audience and lifetime this module
checked itself.

- Only asymmetric algorithms are accepted (``ES256``, ``RS256``). ``none`` and every ``HS*`` algorithm are refused before
  any key is looked at, so a token "signed" with the public key as an HMAC secret cannot pass (algorithm confusion).
- The key is chosen by the token's ``kid`` from the provider's JWKS. The key's type must match the algorithm, and a JWK that
  names its own ``alg`` must name the token's.
- The JWKS is cached for ``jwks_ttl`` seconds. An unknown ``kid`` triggers a refetch, at most once per ``jwks_min_refetch``
  seconds, so a stream of made-up kids cannot turn the server into a request amplifier against the provider.
- ``exp``, ``iat``, ``sub``, ``aud`` and ``iss`` are required; ``nbf`` is honoured when present; a small leeway allows clock skew.
- ``sub`` must be a UUID, and a ``role`` claim, when present, must be ``authenticated`` (the anon and service-role JWTs of a
  legacy project carry no user and are refused).

Nothing here logs a token or a claim value.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable

import httpx
import jwt
from jwt.exceptions import InvalidTokenError, PyJWKError

log = logging.getLogger("auditor.accounts")

ALLOWED_ALGS = {"ES256": "EC", "RS256": "RSA"}   # algorithm -> required JWK key type
MAX_TOKEN_BYTES = 8192


class TokenError(Exception):
    """The token is missing, malformed, unsigned, expired, for another audience or issuer, or signed by an unknown key.
    The message is a short machine reason (never the token); it is not shown to the writer."""


@dataclass(frozen=True)
class Principal:
    user_id: str      # the verified ``sub``
    token: str        # the raw access token, forwarded to PostgREST so Row-Level Security applies to the same user
    expires_at: int
    email: str | None = None

    @property
    def token_hash(self) -> str:
        return hashlib.sha256(self.token.encode()).hexdigest()

    def __repr__(self) -> str:  # never print the token
        return f"Principal(user_id={self.user_id!r})"


class JWKSCache:
    def __init__(self, url: str, ttl: float, min_refetch: float, client: httpx.Client | None = None, timeout: float = 5.0,
                 clock: Callable[[], float] = time.monotonic):
        self.url, self.ttl, self.min_refetch, self.timeout = url, ttl, min_refetch, timeout
        self._client = client
        self._clock = clock
        self._keys: dict[str, dict] = {}
        self._fetched_at: float | None = None
        self._last_attempt: float | None = None
        self._lock = threading.Lock()
        self.fetches = 0   # for tests: how many times the JWKS was requested

    def _fetch(self) -> None:
        self._last_attempt = self._clock()
        self.fetches += 1
        try:
            if self._client is not None:
                res = self._client.get(self.url, timeout=self.timeout)
            else:
                res = httpx.get(self.url, timeout=self.timeout)
            res.raise_for_status()
            keys = res.json().get("keys", [])
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            log.warning("jwks fetch failed: %s", type(exc).__name__)
            return
        self._keys = {k["kid"]: k for k in keys if isinstance(k, dict) and isinstance(k.get("kid"), str)}
        self._fetched_at = self._clock()

    def get(self, kid: str) -> dict | None:
        with self._lock:
            now = self._clock()
            fresh = self._fetched_at is not None and now - self._fetched_at < self.ttl
            if not fresh:
                self._fetch()
            elif kid not in self._keys and (self._last_attempt is None or now - self._last_attempt >= self.min_refetch):
                self._fetch()   # a key rotation: the provider published a new key since the last fetch
            return self._keys.get(kid)


class TokenVerifier:
    def __init__(self, jwks: JWKSCache, issuer: str, audience: str, leeway: float = 30.0):
        self.jwks, self.issuer, self.audience, self.leeway = jwks, issuer, audience, leeway

    def verify(self, token: str) -> Principal:
        if not token or len(token) > MAX_TOKEN_BYTES or token.count(".") != 2:
            raise TokenError("malformed")
        try:
            header = jwt.get_unverified_header(token)
        except InvalidTokenError:
            raise TokenError("malformed header") from None
        alg = header.get("alg")
        if alg not in ALLOWED_ALGS:   # refuses "none", HS256/384/512 and anything unexpected, before any key is used
            raise TokenError("algorithm not allowed")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise TokenError("no kid")
        jwk = self.jwks.get(kid)
        if jwk is None:
            raise TokenError("unknown kid")
        if jwk.get("kty") != ALLOWED_ALGS[alg] or (jwk.get("alg") and jwk.get("alg") != alg) or jwk.get("use", "sig") != "sig":
            raise TokenError("key does not match algorithm")
        try:
            key = jwt.PyJWK(jwk, algorithm=alg).key
            claims = jwt.decode(
                token, key=key, algorithms=[alg], audience=self.audience, issuer=self.issuer, leeway=self.leeway,
                options={"require": ["exp", "iat", "sub", "aud", "iss"], "verify_signature": True},
            )
        except (InvalidTokenError, PyJWKError) as exc:
            raise TokenError(type(exc).__name__) from None
        sub = claims.get("sub")
        try:
            sub = str(uuid.UUID(str(sub)))
        except ValueError:
            raise TokenError("sub is not a user id") from None
        role = claims.get("role")
        if role is not None and role != "authenticated":
            raise TokenError("role")
        email = claims.get("email") if isinstance(claims.get("email"), str) else None
        return Principal(user_id=sub, token=token, expires_at=int(claims["exp"]), email=email)


class Denylist:
    """Tokens and users refused on THIS server instance until the tokens would have expired anyway: a token the writer
    signed out with, and every token of a deleted account. Best effort and per instance (memory only): a JWT stays valid at
    the provider until it expires, so with several instances a replay may reach another one, where it finds no rows."""

    def __init__(self, clock: Callable[[], float] = time.time):
        self._tokens: dict[str, float] = {}
        self._users: dict[str, float] = {}
        self._clock = clock
        self._lock = threading.Lock()

    def _prune(self) -> None:
        now = self._clock()
        for d in (self._tokens, self._users):
            for k in [k for k, until in d.items() if until < now]:
                d.pop(k, None)

    def revoke_token(self, p: Principal, leeway: float) -> None:
        with self._lock:
            self._prune()
            self._tokens[p.token_hash] = p.expires_at + leeway

    def revoke_user(self, user_id: str, until: float) -> None:
        with self._lock:
            self._prune()
            self._users[user_id] = until

    def refused(self, p: Principal) -> bool:
        with self._lock:
            now = self._clock()
            return self._tokens.get(p.token_hash, -1) >= now or self._users.get(p.user_id, -1) >= now
