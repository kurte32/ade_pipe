"""Local OIDC issuer for development.

Issues RS256 access tokens with the same claim shape as Microsoft Entra ID v2 access tokens
(iss, aud, tid, oid, sub, name, preferred_username, roles, scp, azp, ver, iat, nbf, exp) and
serves the discovery document and JWKS. It is a real issuer with its own key pair, not a mock:
the API validates these tokens with exactly the same code path it uses for Entra.

Never deploy this service. The API refuses AUTH_MODE=dev when ENVIRONMENT=production.
"""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

PUBLIC_URL = os.environ.get("DEV_IDP_PUBLIC_URL", "http://localhost:8001").rstrip("/")
TENANT_ID = os.environ.get("DEV_TENANT_ID", "11111111-1111-4111-8111-111111111111")
API_CLIENT_ID = os.environ.get("DEV_API_CLIENT_ID", "22222222-2222-4222-8222-222222222222")
KEY_PATH = Path(os.environ.get("DEV_IDP_KEY_PATH", "/keys/dev-idp.pem"))
TOKEN_TTL_SECONDS = int(os.environ.get("DEV_IDP_TOKEN_TTL", "3600"))
USERS_PATH = Path(__file__).with_name("users.json")

ISSUER = f"{PUBLIC_URL}/{TENANT_ID}/v2.0"


def _load_or_create_key() -> rsa.RSAPrivateKey:
    if KEY_PATH.exists():
        return serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)  # type: ignore[return-value]
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    try:
        KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        KEY_PATH.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    except OSError:
        pass  # ephemeral key when the volume is not writable
    return key


PRIVATE_KEY = _load_or_create_key()
PUBLIC_NUMBERS = PRIVATE_KEY.public_key().public_numbers()
KID = uuid.uuid5(uuid.NAMESPACE_URL, str(PUBLIC_NUMBERS.n)).hex[:16]
USERS: list[dict] = json.loads(USERS_PATH.read_text(encoding="utf-8"))


def _b64url(n: int) -> str:
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


app = FastAPI(title="dev-idp", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class TokenRequest(BaseModel):
    user_code: str
    client_id: str
    scope: str = "access_as_user"


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "issuer": ISSUER, "users": len(USERS)}


@app.get("/{tenant}/v2.0/.well-known/openid-configuration")
def discovery(tenant: str) -> dict:
    if tenant != TENANT_ID:
        raise HTTPException(404)
    return {
        "issuer": ISSUER,
        "jwks_uri": f"{PUBLIC_URL}/{TENANT_ID}/discovery/v2.0/keys",
        "token_endpoint": f"{PUBLIC_URL}/token",
        "id_token_signing_alg_values_supported": ["RS256"],
    }


@app.get("/{tenant}/discovery/v2.0/keys")
def jwks(tenant: str) -> dict:
    if tenant != TENANT_ID:
        raise HTTPException(404)
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": KID,
                "n": _b64url(PUBLIC_NUMBERS.n),
                "e": _b64url(PUBLIC_NUMBERS.e),
            }
        ]
    }


@app.get("/users")
def users() -> list[dict]:
    """Dev directory. Used by the SPA user picker and by the API when DIRECTORY_MODE=dev."""
    return USERS


@app.post("/token")
def token(req: TokenRequest) -> dict:
    user = next((u for u in USERS if u["code"] == req.user_code), None)
    if user is None:
        raise HTTPException(400, "unknown dev user")
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": API_CLIENT_ID,
        "tid": TENANT_ID,
        "oid": user["oid"],
        "sub": user["oid"],
        "name": user["name"],
        "preferred_username": user["email"],
        "roles": user["roles"],
        "scp": req.scope,
        "azp": req.client_id,
        "ver": "2.0",
        "iat": now,
        "nbf": now,
        "exp": now + TOKEN_TTL_SECONDS,
    }
    access_token = jwt.encode(claims, PRIVATE_KEY, algorithm="RS256", headers={"kid": KID})
    return {
        "token_type": "Bearer",
        "expires_in": TOKEN_TTL_SECONDS,
        "access_token": access_token,
        "account": {
            "oid": user["oid"],
            "name": user["name"],
            "username": user["email"],
            "roles": user["roles"],
        },
    }
