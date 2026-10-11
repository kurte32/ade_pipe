"""Audit log writer. Called inside the same transaction as the business write."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import to_utc_naive, utcnow
from app.core.logging import current_correlation_id
from app.core.security import Claims
from app.models import Auditoria


def record(
    session: Session,
    claims: Claims,
    accion: str,
    entidad: str,
    entidad_id: Any,
    detalle: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    session.add(
        Auditoria(
            fecha_utc=to_utc_naive(utcnow()),
            usuario_oid=claims.oid,
            rol=claims.primary_role,
            accion=accion,
            entidad=entidad,
            entidad_id=str(entidad_id),
            ip=ip,
            correlation_id=current_correlation_id() or None,
            detalle=json.dumps(detalle, default=str, ensure_ascii=False) if detalle else None,
        )
    )
