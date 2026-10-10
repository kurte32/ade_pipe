"""Bearer token validation (ADR-006).

One validation path for Entra ID and for the local dev issuer: signature via JWKS, issuer,
audience, expiry, tenant, delegated scope, authorized client (azp), and app roles.
The coordinator identity is always the `oid` claim. It is never read from a parameter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import Settings, get_settings
from app.core.errors import AppError

ROLE_COORDINADOR = "Coordinador"
ROLE_ADMIN = "Admin"
KNOWN_ROLES = (ROLE_ADMIN, ROLE_COORDINADOR)


@dataclass(frozen=True)
class Claims:
    oid: UUID
    name: str
    username: str
    roles: tuple[str, ...]
    azp: str
    tid: str
    raw: dict[str, object] = field(default_factory=dict, repr=False, compare=False)

    @property
    def primary_role(self) -> str:
        for r in KNOWN_ROLES:
            if r in self.roles:
                return r
        return "Ninguno"

    @property
    def is_admin(self) -> bool:
        return ROLE_ADMIN in self.roles

    @property
    def is_coordinador(self) -> bool:
        return ROLE_COORDINADOR in self.roles


@lru_cache
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=3600)


def _unauthorized(detail: str) -> AppError:
    return AppError(401, "unauthorized", "No autorizado", detail)


def validate_token(token: str, settings: Settings) -> Claims:
    try:
        signing_key = _jwks_client(settings.auth_jwks_url).get_signing_key_from_jwt(token).key
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.auth_audience,
            issuer=settings.auth_issuer,
            options={"require": ["exp", "iss", "aud", "iat"]},
            leeway=30,
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized("Token inválido o expirado") from exc

    if str(payload.get("tid", "")) != settings.auth_tenant_id:
        raise _unauthorized("Token de otro tenant")
    scopes = str(payload.get("scp", "")).split()
    if settings.auth_required_scope not in scopes:
        raise _unauthorized("Token sin scope delegado; no se aceptan tokens de aplicación")
    azp = str(payload.get("azp", ""))
    if settings.allowed_azp and azp not in settings.allowed_azp:
        raise _unauthorized("Cliente no autorizado")
    oid_raw = payload.get("oid")
    try:
        oid = UUID(str(oid_raw))
    except (TypeError, ValueError) as exc:
        raise _unauthorized("Token sin identificador de usuario") from exc
    roles_raw = payload.get("roles", [])
    roles = tuple(str(r) for r in roles_raw) if isinstance(roles_raw, list) else ()
    return Claims(
        oid=oid,
        name=str(payload.get("name", "")),
        username=str(payload.get("preferred_username", "")),
        roles=roles,
        azp=azp,
        tid=str(payload.get("tid")),
        raw=dict(payload),
    )


_bearer = HTTPBearer(auto_error=False)


def get_claims(
    request: Request,
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> Claims:
    if cred is None or cred.scheme.lower() != "bearer":
        raise _unauthorized("Falta el encabezado Authorization")
    claims = validate_token(cred.credentials, settings)
    request.state.claims = claims
    return claims


def require_role(*allowed: str):  # type: ignore[no-untyped-def]
    def checker(claims: Claims = Depends(get_claims)) -> Claims:
        if not set(claims.roles) & set(allowed):
            raise AppError(403, "forbidden", "Sin permiso", "No tienes permiso para esta acción")
        return claims

    return checker
