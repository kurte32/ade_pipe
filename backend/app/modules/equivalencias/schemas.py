from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

CODIGO_PATTERN = r"^[a-z]{3,10}$"
CORREO_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class EquivalenciaIn(BaseModel):
    usuario_codigo: str = Field(pattern=CODIGO_PATTERN)
    correo: str = Field(pattern=CORREO_PATTERN, max_length=200)
    activo: bool = True


class EquivalenciaBody(BaseModel):
    correo: str = Field(pattern=CORREO_PATTERN, max_length=200)
    activo: bool = True


class EquivalenciaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    usuario_codigo: str
    correo: str
    oid: str | None
    nombre: str | None
    activo: bool
    actualizado_utc: datetime
