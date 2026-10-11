"""Delete Idempotency-Key replay records older than IDEMPOTENCY_TTL_DAYS."""

from __future__ import annotations

from datetime import timedelta

import structlog
from sqlalchemy import delete

from app.core.clock import to_utc_naive, utcnow
from app.core.config import get_settings
from app.core.db import system_session
from app.models import OperacionIdempotente

log = structlog.get_logger()


def run() -> int:
    cutoff = to_utc_naive(utcnow() - timedelta(days=get_settings().idempotency_ttl_days))
    with system_session() as session:
        res = session.execute(
            delete(OperacionIdempotente).where(OperacionIdempotente.creado_utc < cutoff)
        )
        n = int(getattr(res, "rowcount", 0) or 0)
    if n:
        log.info("idempotency_cleanup", deleted=n)
    return n
