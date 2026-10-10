from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import to_utc_naive
from app.core.errors import unprocessable
from app.core.security import ROLE_ADMIN, Claims, require_role
from app.deps import get_session
from app.models import Auditoria
from app.modules.auditoria.schemas import AuditoriaItem, AuditoriaPage

router = APIRouter(prefix="/api/v1/admin/auditoria", tags=["auditoria"])
MAX_LIMIT = 200


def _item(a: Auditoria) -> AuditoriaItem:
    detalle = None
    if a.detalle:
        try:
            detalle = json.loads(a.detalle)
        except ValueError:
            detalle = None
    return AuditoriaItem(
        id=a.id,
        fecha_utc=a.fecha_utc,
        usuario_oid=a.usuario_oid,
        rol=a.rol,
        accion=a.accion,
        entidad=a.entidad,
        entidad_id=a.entidad_id,
        correlation_id=a.correlation_id,
        detalle=detalle,
    )


@router.get("", response_model=AuditoriaPage)
def list_auditoria(
    usuario_oid: UUID | None = None,
    entidad: str | None = Query(default=None, max_length=40),
    entidad_id: str | None = Query(default=None, max_length=60),
    accion: str | None = Query(default=None, max_length=60),
    desde: datetime | None = None,
    hasta: datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    claims: Claims = Depends(require_role(ROLE_ADMIN)),
    session: Session = Depends(get_session),
) -> AuditoriaPage:
    stmt = select(Auditoria)
    if usuario_oid is not None:
        stmt = stmt.where(Auditoria.usuario_oid == usuario_oid)
    if entidad:
        stmt = stmt.where(Auditoria.entidad == entidad)
    if entidad_id:
        stmt = stmt.where(Auditoria.entidad_id == entidad_id)
    if accion:
        stmt = stmt.where(Auditoria.accion == accion)
    if desde is not None:
        stmt = stmt.where(Auditoria.fecha_utc >= to_utc_naive(desde))
    if hasta is not None:
        stmt = stmt.where(Auditoria.fecha_utc <= to_utc_naive(hasta))
    if cursor:
        if not cursor.isdigit():
            raise unprocessable("cursor inválido")
        stmt = stmt.where(Auditoria.id < int(cursor))
    rows = list(session.execute(stmt.order_by(Auditoria.id.desc()).limit(limit + 1)).scalars())
    next_cursor = str(rows[limit - 1].id) if len(rows) > limit else None
    return AuditoriaPage(items=[_item(a) for a in rows[:limit]], next_cursor=next_cursor)
