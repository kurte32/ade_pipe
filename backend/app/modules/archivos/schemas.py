from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SubidaCreate(BaseModel):
    sitio_id: int
    tipo: str = Field(pattern="^(foto|documento)$")
    tipo_documento: str | None = Field(default=None, max_length=50)
    nombre_original: str = Field(min_length=1, max_length=260)
    content_type: str = Field(min_length=3, max_length=100)
    bytes_total: int = Field(gt=0)
    sha256: str = Field(pattern="^[0-9a-fA-F]{64}$")


class SubidaOut(BaseModel):
    id: str
    sitio_id: int
    tipo: str
    tipo_documento: str | None = None
    estado: str
    tamano_parte: int
    partes_total: int
    partes_recibidas: list[int]
    expira_utc: datetime
    motivo_rechazo: str | None = None
    archivo_id: str | None = None


class PartesOut(BaseModel):
    partes_recibidas: list[int]


class ArchivoMeta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    sitio_id: int
    tipo: str
    tipo_documento: str | None = None
    nombre_original: str
    content_type: str
    sha256: str
    bytes: int
    paginas: int | None = None
    version: int
    vigente: bool
    estado: str
    subido_utc: datetime
    purga_utc: datetime | None = None


class CompletarEscaneando(BaseModel):
    estado: str = "escaneando"
    id: str
