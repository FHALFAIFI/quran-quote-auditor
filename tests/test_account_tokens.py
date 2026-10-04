"""Token verification (roadmap Stage 2, acceptance test 3), against locally generated ES256/RS256 keys and a JWKS served
by a fake (httpx MockTransport). No real Supabase project is involved."""

import json
import time

import pytest

from app.accounts.tokens import Denylist, JWKSCache, TokenError, TokenVerifier
from tests.accounts_helpers import (
    ISSUER, JWKS_URL, USER_A, FakeJWKSServer, Keys, hs256_token, tamper, token, unsigned_token,
)


@pytest.fixture(scope="module")
def keys():
    return Keys()


def make(keys, leeway=30.0, clock=None, fake=None):
    fake = fake or FakeJWKSServer(keys.jwks())
    kw = {"clock": clock} if clock else {}
    cache = JWKSCache(JWKS_URL, ttl=600, min_refetch=30, client=fake.client(), **kw)
    return TokenVerifier(cache, ISSUER, "authenticated", leeway), fake


def refused(v, tok):
    with pytest.raises(TokenError):
        v.verify(tok)


def test_valid_es256_and_rs256(keys):
    v, _ = make(keys)
    for alg in ("ES256", "RS256"):
        p = v.verify(token(keys, alg=alg))
        assert p.user_id == USER_A
        assert USER_A in repr(p) and "eyJ" not in repr(p)   # the token is never printed


def test_expired_and_leeway(keys):
    v, _ = make(keys, leeway=30)
    now = int(time.time())
    refused(v, token(keys, exp=now - 120, iat=now - 3700))
    assert v.verify(token(keys, exp=now - 10, iat=now - 3600)).user_id == USER_A   # within the small leeway


def test_not_yet_valid(keys):
    v, _ = make(keys, leeway=30)
    now = int(time.time())
    refused(v, token(keys, nbf=now + 600))
    refused(v, token(keys, iat=now + 600))


def test_wrong_audience_and_issuer(keys):
    v, _ = make(keys)
    refused(v, token(keys, aud="anon"))
    refused(v, token(keys, aud="someone-else"))
    refused(v, token(keys, iss="https://evil.example/auth/v1"))
    refused(v, token(keys, iss=ISSUER + "/"))


def test_alg_none_refused(keys):
    v, fake = make(keys)
    refused(v, unsigned_token())
    assert fake.requests == 0   # refused before any key was fetched


def test_hs256_signed_with_public_key_refused(keys):
    v, _ = make(keys)
    refused(v, hs256_token(keys.public_pem("ec")))
    refused(v, hs256_token(keys.public_pem("rsa"), kid="rsa-1"))
    refused(v, hs256_token(json.dumps(keys.jwks()["keys"][0]).encode()))


def test_tampered_payload_refused(keys):
    v, _ = make(keys)
    good = token(keys)
    refused(v, tamper(good, sub="bbbbbbbb-0000-4000-8000-00000000000b"))
    refused(v, tamper(good, exp=int(time.time()) + 10**6))
    rs = token(keys, alg="RS256")
    refused(v, tamper(rs, role="service_role"))


def test_unknown_kid_and_bounded_refetch(keys):
    t = [1000.0]
    v, fake = make(keys, clock=lambda: t[0])
    assert v.verify(token(keys)).user_id == USER_A
    assert fake.requests == 1
    stranger = token(keys, kid="not-published", key=keys.other_ec)
    for _ in range(20):
        refused(v, stranger)
    assert fake.requests == 1   # within min_refetch: no request per made-up kid
    t[0] += 31
    refused(v, stranger)
    assert fake.requests == 2   # one refetch after the interval, then refused
    for _ in range(20):
        refused(v, stranger)
    assert fake.requests == 2


def test_key_rotation_picks_up_new_kid(keys):
    t = [1000.0]
    v, fake = make(keys, clock=lambda: t[0])
    v.verify(token(keys))
    fake.jwks = {"keys": fake.jwks["keys"] + [keys.jwk(keys.other_ec, "ec-2", "ES256")]}
    t[0] += 31
    assert v.verify(token(keys, kid="ec-2", key=keys.other_ec)).user_id == USER_A


def test_jwks_ttl_refreshes(keys):
    t = [1000.0]
    v, fake = make(keys, clock=lambda: t[0])
    v.verify(token(keys))
    t[0] += 601
    v.verify(token(keys))
    assert fake.requests == 2


def test_jwks_unreachable_refuses(keys):
    fake = FakeJWKSServer(keys.jwks())
    fake.fail = True
    v, _ = make(keys, fake=fake)
    refused(v, token(keys))


def test_missing_or_bad_sub_and_role(keys):
    v, _ = make(keys)
    refused(v, token(keys, sub=None))
    refused(v, token(keys, sub="not-a-uuid"))
    refused(v, token(keys, role="anon"))
    refused(v, token(keys, role="service_role"))
    refused(v, token(keys, exp=None))


def test_key_type_must_match_alg(keys):
    v, _ = make(keys)
    # an ES256 header pointing at the RSA key, and RS256 pointing at the EC key
    refused(v, token(keys, alg="ES256", kid="rsa-1"))
    refused(v, token(keys, alg="RS256", kid="ec-1"))


def test_garbage_refused(keys):
    v, _ = make(keys)
    for bad in ("", "abc", "a.b", "a.b.c", "x" * 9000, "Bearer " + token(keys)):
        refused(v, bad)


def test_denylist(keys):
    v, _ = make(keys)
    p = v.verify(token(keys))
    d = Denylist()
    assert not d.refused(p)
    d.revoke_token(p, 30)
    assert d.refused(p)
    q = v.verify(token(keys, iat=int(time.time()) - 1))
    d2 = Denylist()
    d2.revoke_user(q.user_id, time.time() + 60)
    assert d2.refused(q) and d2.refused(p)
