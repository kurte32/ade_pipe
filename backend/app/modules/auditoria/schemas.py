from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AuditoriaItem(BaseModel):
    id: int
    fecha_utc: datetime
    usuario_oid: UUID
    rol: str
    accion: str
    entidad: str
    entidad_id: str
    correlation_id: str | None
    detalle: dict[str, Any] | list[Any] | None


class AuditoriaPage(BaseModel):
    items: list[AuditoriaItem]
    next_cursor: str | None = None
