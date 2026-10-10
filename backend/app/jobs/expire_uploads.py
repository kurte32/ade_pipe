"""Expire abandoned upload sessions and delete their staging blobs."""

from __future__ import annotations

import structlog
from sqlalchemy import select

from app.core.clock import to_utc_naive, utcnow
from app.core.db import system_session
from app.core.storage import get_blob_store
from app.models import SubidaSesion
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
        if rows:
            log.info("uploads_expired", count=len(rows))
