"""Shared helpers for the account tests: locally generated signing keys, a JWKS served by a fake (httpx MockTransport),
token minting, and a fixture-style context manager that reloads app.main with the accounts flag on.

Everything here is local. No Supabase project exists; nothing is sent to the network."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import importlib
import json
import os
import time
import uuid

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

SUPABASE_URL = "https://test-project.supabase.example"
ISSUER = f"{SUPABASE_URL}/auth/v1"
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
ANON_KEY = "anon-public-test-key"
SERVICE_KEY = "service-role-SECRET-test-key"
USER_A = str(uuid.UUID("aaaaaaaa-0000-4000-8000-00000000000a"))
USER_B = str(uuid.UUID("bbbbbbbb-0000-4000-8000-00000000000b"))


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class Keys:
    def __init__(self):
        self.ec = ec.generate_private_key(ec.SECP256R1())
        self.rsa = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.other_ec = ec.generate_private_key(ec.SECP256R1())   # never published in the JWKS

    def jwk(self, private, kid: str, alg: str) -> dict:
        algo = jwt.algorithms.ECAlgorithm if alg == "ES256" else jwt.algorithms.RSAAlgorithm
        d = json.loads(algo.to_jwk(private.public_key()))
        d.update({"kid": kid, "alg": alg, "use": "sig"})
        return d

    def jwks(self) -> dict:
        return {"keys": [self.jwk(self.ec, "ec-1", "ES256"), self.jwk(self.rsa, "rsa-1", "RS256")]}

    def public_pem(self, which="ec") -> bytes:
        k = self.ec if which == "ec" else self.rsa
        return k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def claims(sub=USER_A, **over) -> dict:
    now = int(time.time())
    c = {"sub": sub, "aud": "authenticated", "iss": ISSUER, "iat": now, "exp": now + 3600, "role": "authenticated",
         "email": f"{(sub or 'x')[:4]}@example.test"}
    c.update(over)
    return {k: v for k, v in c.items() if v is not None}


def token(keys: Keys, sub=USER_A, alg="ES256", kid=None, key=None, **over) -> str:
    key = key or (keys.ec if alg == "ES256" else keys.rsa)
    kid = kid or ("ec-1" if alg == "ES256" else "rsa-1")
    return jwt.encode(claims(sub, **over), key, algorithm=alg, headers={"kid": kid})


def unsigned_token(sub=USER_A, kid="ec-1") -> str:
    header = b64(json.dumps({"alg": "none", "typ": "JWT", "kid": kid}).encode())
    return f"{header}.{b64(json.dumps(claims(sub)).encode())}."


def hs256_token(secret: bytes, sub=USER_A, kid="ec-1") -> str:
    header = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": kid}).encode())
    payload = b64(json.dumps(claims(sub)).encode())
    sig = hmac.new(secret, f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{b64(sig)}"


def tamper(tok: str, **over) -> str:
    h, p, s = tok.split(".")
    payload = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
    payload.update(over)
    return f"{h}.{b64(json.dumps(payload).encode())}.{s}"


class FakeJWKSServer:
    """A JWKS endpoint served through httpx.MockTransport: counts requests, can rotate keys or fail."""

    def __init__(self, jwks: dict):
        self.jwks, self.requests, self.fail = jwks, 0, False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        assert request.url == httpx.URL(JWKS_URL)
        assert "authorization" not in request.headers     # fetching keys needs no credential
        if self.fail:
            return httpx.Response(503)
        return httpx.Response(200, json=self.jwks)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


ENV = {"ACCOUNTS_ENABLED": "true", "SUPABASE_URL": SUPABASE_URL, "SUPABASE_ANON_KEY": ANON_KEY, "ACCOUNT_RATE_LIMIT_PER_MINUTE": "100000"}


@contextlib.contextmanager
def accounts_main(env: dict | None = None, keys: Keys | None = None, store=None):
    """Reload app.main with the accounts flag on (plus ``env``), wire a fake JWKS and a store, and restore everything after."""
    import app.main as main
    from app.accounts.store import MemoryStore
    from app.accounts.tokens import JWKSCache, TokenVerifier

    saved = {k: os.environ.get(k) for k in set(ENV) | set(env or {}) | {"SUPABASE_SERVICE_ROLE_KEY"}}
    try:
        os.environ.update(ENV)
        os.environ.update(env or {})
        importlib.reload(main)
        ctx = main.app.state.accounts
        keys = keys or Keys()
        fake = FakeJWKSServer(keys.jwks())
        jwks = JWKSCache(ctx.cfg.jwks_url, ctx.cfg.jwks_ttl, ctx.cfg.jwks_min_refetch, client=fake.client())
        ctx.verifier = TokenVerifier(jwks, ctx.cfg.issuer, ctx.cfg.audience, ctx.cfg.leeway)
        ctx.store = store if store is not None else MemoryStore(ctx.cfg.max_drafts)
        yield main, ctx, keys, fake
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        importlib.reload(main)
