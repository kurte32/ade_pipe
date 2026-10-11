"""Idempotency-Key replay store for writes coming from the offline queue (ADR-005)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import to_utc_naive, utcnow
from app.core.errors import unprocessable
from app.core.security import Claims
from app.models import OperacionIdempotente

MAX_KEY_LEN = 80


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
    if row.ruta != route or row.hash_cuerpo != body_hash:
        raise unprocessable("Idempotency-Key reutilizada con otra petición")
    return row.codigo_respuesta, json.loads(row.cuerpo_respuesta)


def store(
    session: Session,
    claims: Claims,
    key: str | None,
    route: str,
    body_hash: str,
    status: int,
    body: Any,
) -> None:
    if not key:
        return
    session.add(
        OperacionIdempotente(
            clave=key,
            usuario_oid=claims.oid,
            ruta=route,
            hash_cuerpo=body_hash,
            codigo_respuesta=status,
            cuerpo_respuesta=json.dumps(body, default=str, ensure_ascii=False),
            creado_utc=to_utc_naive(utcnow()),
        )
    )
