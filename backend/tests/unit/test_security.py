"""Token validation negatives from the Entra guide (C5) plus the ADR-006 hardening, without the network."""

from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core import security
from app.core.config import Settings
from app.core.errors import AppError

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TENANT = "11111111-1111-4111-8111-111111111111"
AUD = "22222222-2222-4222-8222-222222222222"
PWA = "33333333-3333-4333-8333-333333333333"
ISS = f"https://login.microsoftonline.com/{TENANT}/v2.0"


class _FakeKey:
    def __init__(self, key: Any) -> None:
        self.key = key


class _FakeJwks:
    def get_signing_key_from_jwt(self, token: str) -> _FakeKey:
        return _FakeKey(KEY.public_key())


@pytest.fixture(autouse=True)
def _fake_jwks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "_jwks_client", lambda url: _FakeJwks())


@pytest.fixture
def settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        auth_tenant_id=TENANT,
        auth_audience=AUD,
        auth_allowed_azp=PWA,
        auth_issuer=ISS,
        auth_jwks_url="https://example.invalid/keys",
    )


def token(key: Any = KEY, **over: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": ISS,
        "aud": AUD,
        "tid": TENANT,
        "oid": "a0000000-0000-4000-8000-000000000001",
        "name": "Ana",
        "preferred_username": "ard@x",
        "roles": ["Coordinador"],
        "scp": "access_as_user",
        "azp": PWA,
        "iat": now,
        "nbf": now,
        "exp": now + 600,
    }
    claims.update(over)
    for k in [k for k, v in claims.items() if v is None]:
        del claims[k]
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


def test_valid_token(settings: Settings) -> None:
    c = security.validate_token(token(), settings)
    assert str(c.oid) == "a0000000-0000-4000-8000-000000000001"
    assert c.roles == ("Coordinador",)
    assert c.primary_role == "Coordinador"


@pytest.mark.parametrize(
    "over",
    [
        {"exp": int(time.time()) - 120},
        {"aud": "other"},
        {"iss": "https://sts.windows.net/x/"},
        {"tid": "99999999-9999-4999-8999-999999999999"},
        {"scp": None},
        {"scp": "User.Read"},
        {"azp": "55555555-5555-4555-8555-555555555555"},
        {"oid": None},
        {"oid": "not-a-uuid"},
    ],
)
def test_rejected(settings: Settings, over: dict[str, Any]) -> None:
    with pytest.raises(AppError) as e:
        security.validate_token(token(**over), settings)
    assert e.value.status == 401


def test_wrong_signature(settings: Settings) -> None:
    with pytest.raises(AppError):
        security.validate_token(token(key=OTHER_KEY), settings)


def test_roles_missing_is_still_a_valid_token_but_no_role() -> None:
    s = Settings(  # type: ignore[call-arg]
        auth_tenant_id=TENANT,
        auth_audience=AUD,
        auth_allowed_azp=PWA,
        auth_issuer=ISS,
        auth_jwks_url="x",
    )
    c = security.validate_token(token(roles=None), s)
    assert c.roles == ()
    assert c.primary_role == "Ninguno"


def test_production_guard_refuses_dev_modes() -> None:
    with pytest.raises(ValueError, match="Refusing to start in production"):
        Settings(  # type: ignore[call-arg]
            environment="production",
            auth_tenant_id=TENANT,
            auth_audience=AUD,
            auth_allowed_azp=PWA,
            auth_issuer="http://localhost:8001/x/v2.0",
            auth_jwks_url="x",
        )


def test_unknown_role_from_token_is_dropped(settings: Settings) -> None:
    """A token may carry only recognised app roles; anything else is stripped (audit A2)."""
    c = security.validate_token(token(roles=["Sistema"]), settings)
    assert c.roles == ()
    assert c.primary_role == "Ninguno"  # never reaches SESSION_CONTEXT('rol') as a privileged role
    c2 = security.validate_token(token(roles=["Coordinador", "Sistema", "whatever"]), settings)
    assert c2.roles == ("Coordinador",)


def test_alg_none_token_rejected(settings: Settings) -> None:
    """An unsigned (alg:none) token must be rejected (audit C10)."""
    unsigned = jwt.encode(
        {
            "iss": ISS,
            "aud": AUD,
            "tid": TENANT,
            "oid": "a0000000-0000-4000-8000-000000000001",
            "scp": "access_as_user",
            "azp": PWA,
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
        },
        key=None,
        algorithm="none",
    )
    with pytest.raises(AppError) as e:
        security.validate_token(unsigned, settings)
    assert e.value.status == 401


def test_hs256_signed_with_rsa_public_key_rejected(settings: Settings) -> None:
    """Algorithm-confusion: HS256 signed with the RSA public key must be rejected (audit C10).

    PyJWT's encoder refuses to sign an HMAC token with an asymmetric key, so the token is forged by
    hand (as an attacker would) and the decoder — pinned to RS256 — must reject it.
    """
    import base64
    import hashlib
    import hmac
    import json

    from cryptography.hazmat.primitives import serialization

    pub_pem = KEY.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )

    def b64(raw: bytes) -> bytes:
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": "k1"}).encode())
    payload = b64(
        json.dumps(
            {
                "iss": ISS,
                "aud": AUD,
                "tid": TENANT,
                "oid": "a0000000-0000-4000-8000-000000000001",
                "scp": "access_as_user",
                "azp": PWA,
                "roles": ["Admin"],
                "iat": int(time.time()),
                "exp": int(time.time()) + 600,
            }
        ).encode()
    )
    signing_input = header + b"." + payload
    sig = b64(hmac.new(pub_pem, signing_input, hashlib.sha256).digest())
    forged = (signing_input + b"." + sig).decode()

    with pytest.raises(AppError) as e:
        security.validate_token(forged, settings)
    assert e.value.status == 401


def test_production_guard_refuses_foreign_jwks_url() -> None:
    """A correct issuer with a non-Entra JWKS endpoint must be refused (audit A1)."""
    with pytest.raises(ValueError, match="AUTH_JWKS_URL"):
        Settings(  # type: ignore[call-arg]
            environment="production",
            auth_mode="entra",
            db_auth="entra",
            storage_mode="azure",
            scan_mode="defender",
            notify_mode="graph",
            directory_mode="graph",
            auth_tenant_id=TENANT,
            auth_audience=AUD,
            auth_allowed_azp=PWA,
            auth_issuer=f"https://login.microsoftonline.com/{TENANT}/v2.0",
            auth_jwks_url="https://attacker.example/keys",
        )
