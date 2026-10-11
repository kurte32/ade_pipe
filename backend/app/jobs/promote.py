"""Finish uploads that were waiting for a malware scan result (SCAN_MODE=defender)."""

from __future__ import annotations

from datetime import timedelta

import structlog
from sqlalchemy import select

from app.core.clock import to_utc_naive, utcnow
from app.core.config import get_settings
from app.core.db import system_session
from app.core.storage import get_blob_store
from app.models import SubidaSesion
from app.modules.archivos import service
from app.modules.archivos.scan import get_scanner

log = structlog.get_logger()


def run() -> None:
    settings = get_settings()
    store = get_blob_store()
    scanner = get_scanner(settings, store)
    now = to_utc_naive(utcnow())
    stale_before = now - timedelta(seconds=settings.scan_wait_seconds)
    with system_session() as session:
        pending = list(
            session.execute(
                select(SubidaSesion).where(SubidaSesion.estado == service.ESTADO_ESCANEANDO)
            ).scalars()
        )
        for subida in pending:
            result = scanner.result(subida.blob_staging)
            if result == "clean":
                service.promote(session, service.SYSTEM_CLAIMS, store, settings, subida)
                log.info("upload_promoted", subida_id=str(subida.id))
            elif result == "malicious":
                service.reject(
                    session,
                    service.SYSTEM_CLAIMS,
                    store,
                    subida,
                    "Archivo rechazado por malware",
                    "archivo_rechazado_malware",
                )
                log.warning("upload_rejected_malware", subida_id=str(subida.id))
            elif result == "pending":
                if subida.actualizado_utc < stale_before:
                    log.warning(
                        "scan_result_overdue",
                        subida_id=str(subida.id),
                        waiting_seconds=int((now - subida.actualizado_utc).total_seconds()),
                    )
            else:
                log.error("scan_result_error", subida_id=str(subida.id))
        if pending:
            log.info("promote_job_done", processed=len(pending))
