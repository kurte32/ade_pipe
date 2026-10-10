from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import ROLE_ADMIN, ROLE_COORDINADOR, Claims, require_role

router = APIRouter(prefix="/api/v1", tags=["identity"])


class MeResponse(BaseModel):
    oid: str
    name: str
    username: str
    roles: list[str]


@router.get("/me", response_model=MeResponse)
def me(claims: Claims = Depends(require_role(ROLE_COORDINADOR, ROLE_ADMIN))) -> MeResponse:
    return MeResponse(
        oid=str(claims.oid), name=claims.name, username=claims.username, roles=list(claims.roles)
    )
