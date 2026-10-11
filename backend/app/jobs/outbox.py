"""Deliver pending notifications from the outbox with exponential backoff (ADR-007)."""

from __future__ import annotations

import json
import re
from datetime import timedelta

import structlog
from sqlalchemy import select

from app.core.clock import to_utc_naive, utcnow
from app.core.db import system_session
from app.models import NotificacionOutbox
from app.modules.notificaciones.graph import get_notifier

log = structlog.get_logger()
MAX_ATTEMPTS = 8
BATCH = 100


# Messages our own notifier raises; they carry no tokens, URLs or personal data.
_SAFE_MESSAGE = re.compile(r"^(Graph \d{3}|TEAMS_APP_ID no configurado)$")


def describe_error(exc: BaseException) -> str:
    """Error text stored on the outbox row: the exception type, plus the message only when it is
    one of the known-safe ones. Third-party exception text can embed request URLs, headers or
    tokens, so it is not persisted (audit C9)."""
    msg = str(exc)
    if _SAFE_MESSAGE.match(msg):
        return f"{type(exc).__name__}: {msg}"
    return type(exc).__name__


def run() -> None:
    notifier = get_notifier()
    now = to_utc_naive(utcnow())
    sent = failed = 0
    with system_session() as session:
        rows = list(
            session.execute(
                select(NotificacionOutbox)
                .where(
                    NotificacionOutbox.estado == "pendiente",
                    NotificacionOutbox.siguiente_intento_utc <= now,
                    NotificacionOutbox.intentos < MAX_ATTEMPTS,
                )
                .order_by(NotificacionOutbox.id)
                .limit(BATCH)
            ).scalars()
        )
        for row in rows:
            try:
                body = json.loads(row.cuerpo)
            except ValueError:
                body = {}
            try:
                notifier.send(str(row.destinatario_oid), body)
                row.estado = "enviada"
                row.enviada_utc = to_utc_naive(utcnow())
                row.ultimo_error = None
                sent += 1
            except Exception as exc:  # noqa: BLE001 - any delivery failure is retried
                row.intentos += 1
                row.ultimo_error = describe_error(exc)
                backoff = min(timedelta(minutes=2**row.intentos), timedelta(hours=6))
                row.siguiente_intento_utc = to_utc_naive(utcnow()) + backoff
                if row.intentos >= MAX_ATTEMPTS:
                    row.estado = "fallida"
                failed += 1
    log.info("outbox_run", procesadas=len(rows), enviadas=sent, fallidas=failed)
