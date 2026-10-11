from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import to_utc_naive, utcnow
from app.core.config import get_settings
from app.core.errors import not_found
from app.core.security import Claims
from app.models import NotificacionOutbox, Sitio
from app.modules.notificaciones.schemas import NotificacionList, NotificacionOut


def enqueue_devolucion(
    session: Session,
    sitio: Sitio,
    motivo_codigo: str,
    motivo_nombre: str,
    estatus_destino: str,
    estatus_destino_nombre: str,
    comentario: str,
) -> NotificacionOutbox:
    """Outbox row for the coordinator. Never includes owner contact data."""
    now = to_utc_naive(utcnow())
    base = get_settings().app_public_url.rstrip("/")
    body = {
        "tipo": "devolucion",
        "sitio_id": sitio.id,
        "sitio_nombre": sitio.nombre,
        "estatus_destino": estatus_destino,
        "estatus_destino_nombre": estatus_destino_nombre,
        "motivo": motivo_codigo,
        "motivo_nombre": motivo_nombre,
        "comentario": comentario,
        "url": f"{base}/sitios/{sitio.id}",
    }
    row = NotificacionOutbox(
        sitio_id=sitio.id,
        destinatario_oid=sitio.coordinador_oid,
        tipo="devolucion",
        cuerpo=json.dumps(body, ensure_ascii=False),
        intentos=0,
        estado="pendiente",
        siguiente_intento_utc=now,
        creado_utc=now,
    )
    session.add(row)
    session.flush()
    return row


def _to_out(n: NotificacionOutbox) -> NotificacionOut:
    try:
        cuerpo = json.loads(n.cuerpo)
    except ValueError:
        cuerpo = {}
    return NotificacionOut(
        id=n.id,
        sitio_id=n.sitio_id,
        tipo=n.tipo,
        cuerpo=cuerpo,
        estado=n.estado,
        creado_utc=n.creado_utc,
        leida=n.leida_utc is not None,
        leida_utc=n.leida_utc,
        enviada_utc=n.enviada_utc,
    )


def list_mine(session: Session, claims: Claims, limit: int = 100) -> NotificacionList:
    rows = list(
        session.execute(
            select(NotificacionOutbox)
            .where(NotificacionOutbox.destinatario_oid == claims.oid)
            .order_by(NotificacionOutbox.id.desc())
            .limit(limit)
        ).scalars()
    )
    unread = session.execute(
        select(func.count()).where(
            NotificacionOutbox.destinatario_oid == claims.oid,
            NotificacionOutbox.leida_utc.is_(None),
        )
    ).scalar()
    return NotificacionList(items=[_to_out(r) for r in rows], no_leidas=int(unread or 0))


def marcar_leida(session: Session, claims: Claims, notificacion_id: int) -> NotificacionOut:
    row = session.execute(
        select(NotificacionOutbox).where(
            NotificacionOutbox.id == notificacion_id,
            NotificacionOutbox.destinatario_oid == claims.oid,
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("Notificación")
    if row.leida_utc is None:
        row.leida_utc = to_utc_naive(utcnow())
        session.flush()
    return _to_out(row)
