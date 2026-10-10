from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import ROLE_COORDINADOR, Claims, require_role
from app.deps import get_session
from app.modules.notificaciones import service
from app.modules.notificaciones.schemas import NotificacionList, NotificacionOut

router = APIRouter(prefix="/api/v1/notificaciones", tags=["notificaciones"])
_coord = require_role(ROLE_COORDINADOR)


@router.get("", response_model=NotificacionList)
def list_notificaciones(
    claims: Claims = Depends(_coord), session: Session = Depends(get_session)
) -> NotificacionList:
    return service.list_mine(session, claims)


@router.post("/{notificacion_id}/leer", response_model=NotificacionOut)
def leer(
    notificacion_id: int,
    claims: Claims = Depends(_coord),
    session: Session = Depends(get_session),
) -> NotificacionOut:
    return service.marcar_leida(session, claims, notificacion_id)
