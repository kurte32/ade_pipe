from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class NotificacionOut(BaseModel):
    id: int
    sitio_id: int
    tipo: str
    cuerpo: dict[str, Any]
    estado: str
    creado_utc: datetime
    leida: bool
    leida_utc: datetime | None
    enviada_utc: datetime | None


class NotificacionList(BaseModel):
    items: list[NotificacionOut]
    no_leidas: int
