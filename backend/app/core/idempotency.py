"""Idempotency-Key replay store for writes coming from the offline queue (ADR-005)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import to_utc_naive, utcnow
from app.core.db import set_session_context
from app.core.errors import conflict, unprocessable
from app.core.security import Claims
from app.models import OperacionIdempotente

MAX_KEY_LEN = 80
# Placeholder status for a claimed key whose work has not committed yet.
IN_FLIGHT = 0
IN_FLIGHT_DETAIL = "La operación con este Idempotency-Key sigue en curso; reintenta."


def request_hash(body: Any) -> str:
    payload = json.dumps(body, sort_keys=True, default=str, ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def lookup(
    session: Session, claims: Claims, key: str | None, route: str, body_hash: str
) -> tuple[int, Any] | None:
    """Return the stored (status, body) when the same key was already processed."""
    if not key:
        return None
    if len(key) > MAX_KEY_LEN:
        raise unprocessable("Idempotency-Key demasiado largo")
    row = session.execute(
        select(OperacionIdempotente).where(
            OperacionIdempotente.clave == key, OperacionIdempotente.usuario_oid == claims.oid
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.codigo_respuesta == IN_FLIGHT:
        raise conflict(IN_FLIGHT_DETAIL)
    if row.ruta != route or row.hash_cuerpo != body_hash:
        raise unprocessable("Idempotency-Key reutilizada con otra petición")
    return row.codigo_respuesta, json.loads(row.cuerpo_respuesta)


def run_once(
    session: Session,
    claims: Claims,
    key: str | None,
    route: str,
    body_hash: str,
    work: Callable[[], tuple[int, Any]],
) -> tuple[int, Any]:
    """Run ``work`` at most once per (key, user); replays get the stored (status, body).

    The key is claimed by inserting its row *before* the business write (audit B-02). A concurrent
    duplicate blocks on that row and fails with a duplicate key once the first request commits; it
    then rolls back and returns the response the first request stored. Without a key, ``work`` runs.
    """
    if not key:
        return work()
    stored = lookup(session, claims, key, route, body_hash)
    if stored is not None:
        return stored
    claim = OperacionIdempotente(
        clave=key,
        usuario_oid=claims.oid,
        ruta=route,
        hash_cuerpo=body_hash,
        codigo_respuesta=IN_FLIGHT,
        cuerpo_respuesta="null",
        creado_utc=to_utc_naive(utcnow()),
    )
    session.add(claim)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        # The rollback returned the connection to the pool, which clears the RLS session context.
        set_session_context(session, str(claims.oid), claims.primary_role)
        stored = lookup(session, claims, key, route, body_hash)
        if stored is None:
            raise conflict(IN_FLIGHT_DETAIL) from None
        return stored
    status, body = work()
    claim.codigo_respuesta = status
    claim.cuerpo_respuesta = json.dumps(body, default=str, ensure_ascii=False)
    return status, body
