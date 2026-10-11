from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class LoteSummary(BaseModel):
    id: str
    archivo_nombre: str
    hash: str
    fecha_utc: datetime
    filas_total: int
    filas_ok: int
    filas_advertencia: int
    filas_error: int
    estado: str
    confirmado_utc: datetime | None = None
    filas_insertadas: int | None = None
    filas_actualizadas: int | None = None
    filas_revision: int | None = None
    pendientes_decision: int = 0


class FilaOut(BaseModel):
    num_fila: int
    resultado: str
    motivos: list[dict[str, str]]
    decision_admin: str | None
    origen_id: int | None
    accion_prevista: str | None
    datos: dict[str, Any]
    normalizado: dict[str, Any] | None


class FilasPage(BaseModel):
    items: list[FilaOut]
    next_cursor: str | None = None


class LoteDetail(BaseModel):
    lote: LoteSummary
    filas: FilasPage


class DecisionIn(BaseModel):
    num_fila: int = Field(ge=2)
    decision: Literal["aprobar", "excluir"]


class ConfirmResult(BaseModel):
    lote: LoteSummary
    insertadas: int
    actualizadas: int
    revision: int
