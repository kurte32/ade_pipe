"""Expire abandoned upload sessions and delete their staging blobs."""

from __future__ import annotations

import json

import structlog
from sqlalchemy import select

from app.core.clock import to_utc_naive, utcnow
from app.core.db import SYSTEM_OID, system_session
from app.core.storage import get_blob_store
from app.models import Auditoria, SubidaSesion
from app.modules.archivos import service

log = structlog.get_logger()


def run() -> None:
    store = get_blob_store()
    now = to_utc_naive(utcnow())
    with system_session() as session:
        rows = list(
            session.execute(
                select(SubidaSesion).where(
                    SubidaSesion.estado.in_([service.ESTADO_ABIERTA, service.ESTADO_ESCANEANDO]),
                    SubidaSesion.expira_utc < now,
                )
            ).scalars()
        )
        for subida in rows:
            store.delete("staging", subida.blob_staging)
            subida.estado = service.ESTADO_EXPIRADA
            subida.actualizado_utc = now
            # RNF-07: the staging delete is a write that leaves a trace (audit DAT-13).
            session.add(
                Auditoria(
                    fecha_utc=now,
                    usuario_oid=SYSTEM_OID,
                    rol="Sistema",
                    accion="subida_expirada",
                    entidad="subida_sesion",
                    entidad_id=str(subida.id),
                    ip=None,
                    correlation_id=None,
                    detalle=json.dumps({"sitio_id": subida.sitio_id, "tipo": subida.tipo}),
                )
            )
        if rows:
            log.info("uploads_expired", count=len(rows))
