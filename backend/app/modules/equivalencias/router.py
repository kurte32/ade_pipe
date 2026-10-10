from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.core.security import ROLE_ADMIN, Claims, require_role
from app.deps import get_session
from app.modules.equivalencias import service
from app.modules.equivalencias.schemas import (
    CODIGO_PATTERN,
    EquivalenciaBody,
    EquivalenciaIn,
    EquivalenciaOut,
)

router = APIRouter(prefix="/api/v1/admin/equivalencias", tags=["equivalencias"])
_admin = require_role(ROLE_ADMIN)


@router.get("", response_model=list[EquivalenciaOut])
def list_equivalencias(
    claims: Claims = Depends(_admin), session: Session = Depends(get_session)
) -> list[EquivalenciaOut]:
    return service.list_equivalencias(session)


@router.put("", response_model=list[EquivalenciaOut])
def upsert_equivalencias(
    items: list[EquivalenciaIn],
    claims: Claims = Depends(_admin),
    session: Session = Depends(get_session),
) -> list[EquivalenciaOut]:
    return service.upsert_many(session, claims, items)


@router.put("/{codigo}", response_model=EquivalenciaOut)
def upsert_equivalencia(
    body: EquivalenciaBody,
    codigo: str = Path(pattern=CODIGO_PATTERN),
    claims: Claims = Depends(_admin),
    session: Session = Depends(get_session),
) -> EquivalenciaOut:
    item = EquivalenciaIn(usuario_codigo=codigo, correo=body.correo, activo=body.activo)
    return service.upsert_many(session, claims, [item])[0]
