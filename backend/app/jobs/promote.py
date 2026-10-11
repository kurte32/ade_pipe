"""Finish uploads that were waiting for a malware scan result (SCAN_MODE=defender).

Each upload is processed in its own transaction (audit B-06): a failure on one session is logged
and retried on the next run without rolling back uploads already promoted in the same batch.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import structlog
from sqlalchemy import select

from app.core.clock import to_utc_naive, utcnow
from app.core.config import Settings, get_settings
from app.core.db import system_session
from app.core.storage import BlobStore, get_blob_store
from app.models import SubidaSesion
from app.modules.archivos import service
from app.modules.archivos.scan import Scanner, get_scanner

log = structlog.get_logger()


def _process_one(
    subida_id: uuid.UUID,
    settings: Settings,
    store: BlobStore,
    scanner: Scanner,
    now: datetime,
    stale_before: datetime,
) -> str:
    with system_session() as session:
        subida = session.get(SubidaSesion, subida_id)
        if subida is None or subida.estado != service.ESTADO_ESCANEANDO:
            return "skipped"
        if not store.exists("staging", subida.blob_staging):
            # A previous run copied the blob (only ever done after a clean scan) and deleted
            # staging, but its commit was lost. The scan tag went with staging, so finish the
            # registration from the existing copy instead of waiting forever (audit B-06).
            _, dst = service.document_destination(subida)
            if store.exists("documents", dst):
                service.promote(session, service.SYSTEM_CLAIMS, store, settings, subida)
                log.warning("upload_promoted_after_lost_commit", subida_id=str(subida_id))
                return "clean"
        result = scanner.result(subida.blob_staging)
        if result == "clean":
            service.promote(session, service.SYSTEM_CLAIMS, store, settings, subida)
            log.info("upload_promoted", subida_id=str(subida_id))
        elif result == "malicious":
            service.reject(
                session,
                service.SYSTEM_CLAIMS,
                store,
                subida,
                "Archivo rechazado por malware",
                "archivo_rechazado_malware",
            )
            log.warning("upload_rejected_malware", subida_id=str(subida_id))
        elif result == "pending":
            if subida.actualizado_utc < stale_before:
                log.warning(
                    "scan_result_overdue",
                    subida_id=str(subida_id),
                    waiting_seconds=int((now - subida.actualizado_utc).total_seconds()),
                )
        else:
            log.error("scan_result_error", subida_id=str(subida_id))
        return result


def run() -> dict[str, int]:
    settings = get_settings()
    store = get_blob_store()
    scanner = get_scanner(settings, store)
    now = to_utc_naive(utcnow())
    stale_before = now - timedelta(seconds=settings.scan_wait_seconds)
    with system_session() as session:
        ids = list(
            session.execute(
                select(SubidaSesion.id).where(SubidaSesion.estado == service.ESTADO_ESCANEANDO)
            ).scalars()
        )
    counts: dict[str, int] = {}
    for subida_id in ids:
        try:
            outcome = _process_one(subida_id, settings, store, scanner, now, stale_before)
        except Exception:  # noqa: BLE001 - isolate the failure to this upload; retried next run
            log.exception("promote_failed", subida_id=str(subida_id))
            outcome = "failed"
        counts[outcome] = counts.get(outcome, 0) + 1
    if ids:
        log.info("promote_job_done", processed=len(ids), **counts)
    return counts
