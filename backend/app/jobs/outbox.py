"""Deliver pending notifications from the outbox with exponential backoff (ADR-007)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

import structlog
from sqlalchemy import select, update
from sqlalchemy.orm import Session

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


# A claim older than this belongs to a run that died mid-send; it is released for retry.
CLAIM_TIMEOUT = timedelta(minutes=15)


def _claim(session: Session, now: datetime) -> list[int]:
    """Take a batch of due rows for this run only.

    Scheduled Container Apps runs can overlap; two runs reading the same pending rows sent every
    notification twice (audit DAT-7). The claim is a short transaction that locks the rows it
    reads (UPDLOCK) and skips rows another run holds (READPAST), then marks them `enviando`.
    """
    session.execute(
        update(NotificacionOutbox)
        .where(
            NotificacionOutbox.estado == "enviando",
            NotificacionOutbox.siguiente_intento_utc <= now - CLAIM_TIMEOUT,
        )
        .values(estado="pendiente")
    )
    ids = list(
        session.execute(
            select(NotificacionOutbox.id)
            .where(
                NotificacionOutbox.estado == "pendiente",
                NotificacionOutbox.siguiente_intento_utc <= now,
                NotificacionOutbox.intentos < MAX_ATTEMPTS,
            )
            .order_by(NotificacionOutbox.id)
            .limit(BATCH)
            # with_for_update() renders nothing on SQL Server; READPAST skips rows another run holds
            .with_hint(NotificacionOutbox, "WITH (UPDLOCK, ROWLOCK, READPAST)")
        ).scalars()
    )
    if ids:
        session.execute(
            update(NotificacionOutbox)
            .where(NotificacionOutbox.id.in_(ids))
            .values(estado="enviando", siguiente_intento_utc=now)
        )
    return ids


def run() -> None:
    notifier = get_notifier()
    now = to_utc_naive(utcnow())
    sent = failed = 0
    with system_session() as session:
        ids = _claim(session, now)
    # Each row commits on its own so a run killed by its timeout re-sends at most one message.
    for row_id in ids:
        with system_session() as session:
            row = session.get(NotificacionOutbox, row_id)
            if row is None or row.estado != "enviando":
                continue
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
                row.estado = "fallida" if row.intentos >= MAX_ATTEMPTS else "pendiente"
                failed += 1
    log.info("outbox_run", procesadas=len(ids), enviadas=sent, fallidas=failed)
