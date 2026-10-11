"""Retention purge (RF-11, TDD 9.3): delete expired document blobs, keep the metadata.

In Azure, an immutability policy or legal hold makes the delete fail; the job logs and skips
that file instead of failing, so a legal hold blocks the purge as intended. Each file is handled
in its own transaction (audit B-06), and the blob delete is idempotent, so a lost commit is
completed on the next run.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import structlog
from azure.core.exceptions import HttpResponseError
from sqlalchemy import select

from app.core.clock import to_utc_naive, utcnow
from app.core.db import SYSTEM_OID, system_session
from app.core.storage import BlobStore, get_blob_store
from app.models import Auditoria, Sitio, SitioArchivo

log = structlog.get_logger()


def _purge_one(archivo_id: uuid.UUID, store: BlobStore, now: datetime) -> str:
    with system_session() as session:
        archivo = session.get(SitioArchivo, archivo_id)
        if archivo is None or archivo.estado != "publicado":
            return "skipped"
        try:
            store.delete("documents", archivo.ruta_blob)
        except HttpResponseError as exc:
            log.warning(
                "purge_blocked",
                archivo_id=str(archivo_id),
                reason=type(exc).__name__,
                status=getattr(exc, "status_code", None),
            )
            return "blocked"
        archivo.estado = "purgado"
        archivo.purgado_utc = now
        # Bump the site's version so devices refresh their file list (audit DAT-11).
        sitio = session.get(Sitio, archivo.sitio_id)
        if sitio is not None:
            sitio.actualizado_utc = now
        session.add(
            Auditoria(
                fecha_utc=now,
                usuario_oid=SYSTEM_OID,
                rol="Sistema",
                accion="archivo_purgado",
                entidad="sitio_archivo",
                entidad_id=str(archivo_id),
                ip=None,
                correlation_id=None,
                detalle=json.dumps(
                    {"sitio_id": archivo.sitio_id, "purga_utc": archivo.purga_utc}, default=str
                ),
            )
        )
        return "purged"


def run() -> dict[str, int]:
    store = get_blob_store()
    now = to_utc_naive(utcnow())
    with system_session() as session:
        ids = list(
            session.execute(
                select(SitioArchivo.id).where(
                    SitioArchivo.estado == "publicado",
                    SitioArchivo.purga_utc.is_not(None),
                    SitioArchivo.purga_utc <= now,
                )
            ).scalars()
        )
    counts: dict[str, int] = {}
    for archivo_id in ids:
        try:
            outcome = _purge_one(archivo_id, store, now)
        except Exception:  # noqa: BLE001 - isolate the failure to this file; retried next run
            log.exception("purge_failed", archivo_id=str(archivo_id))
            outcome = "failed"
        counts[outcome] = counts.get(outcome, 0) + 1
    if ids:
        log.info("purge_job_done", processed=len(ids), **counts)
    return counts
