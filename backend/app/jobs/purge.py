"""Retention purge (RF-11, TDD 9.3): delete expired document blobs, keep the metadata.

In Azure, an immutability policy or legal hold makes the delete fail; the job logs and skips
that file instead of failing, so a legal hold blocks the purge as intended.
"""

from __future__ import annotations

import json

import structlog
from azure.core.exceptions import HttpResponseError
from sqlalchemy import select

from app.core.clock import to_utc_naive, utcnow
from app.core.db import SYSTEM_OID, system_session
from app.core.storage import get_blob_store
from app.models import Auditoria, SitioArchivo

log = structlog.get_logger()


def run() -> None:
    store = get_blob_store()
    now = to_utc_naive(utcnow())
    purged = skipped = 0
    with system_session() as session:
        rows = list(
            session.execute(
                select(SitioArchivo).where(
                    SitioArchivo.estado == "publicado",
                    SitioArchivo.purga_utc.is_not(None),
                    SitioArchivo.purga_utc <= now,
                )
            ).scalars()
        )
        for archivo in rows:
            try:
                store.delete("documents", archivo.ruta_blob)
            except HttpResponseError as exc:
                skipped += 1
                log.warning(
                    "purge_blocked",
                    archivo_id=str(archivo.id),
                    reason=type(exc).__name__,
                    status=getattr(exc, "status_code", None),
                )
                continue
            archivo.estado = "purgado"
            archivo.purgado_utc = now
            session.add(
                Auditoria(
                    fecha_utc=now,
                    usuario_oid=SYSTEM_OID,
                    rol="Sistema",
                    accion="archivo_purgado",
                    entidad="sitio_archivo",
                    entidad_id=str(archivo.id),
                    ip=None,
                    correlation_id=None,
                    detalle=json.dumps(
                        {"sitio_id": archivo.sitio_id, "purga_utc": archivo.purga_utc},
                        default=str,
                    ),
                )
            )
            purged += 1
        if rows:
            log.info("purge_job_done", purged=purged, skipped=skipped)
