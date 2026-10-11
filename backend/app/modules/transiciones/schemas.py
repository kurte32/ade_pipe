from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.sitios.schemas import ContactoOut, VisitaOut

_PHONE = re.compile(r"^\d{10,15}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ContactoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    telefono: str = Field(min_length=10, max_length=30)
    correo: str | None = Field(default=None, max_length=200)
    notas: str | None = Field(default=None, max_length=1000)

    @field_validator("telefono")
    @classmethod
    def _phone(cls, v: str) -> str:
        digits = re.sub(r"[\s\-()+]", "", v)
        if not _PHONE.match(digits):
            raise ValueError("El teléfono debe tener entre 10 y 15 dígitos")
        return digits

    @field_validator("correo")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v is None or v.strip() == "":
            return None
        v = v.strip()
        if not _EMAIL.match(v):
            raise ValueError("Correo no válido")
        return v


class ContactoResponse(ContactoOut):
    etag: str


class VisitaIn(BaseModel):
    frente_m: Decimal = Field(gt=0, le=10000)
    fondo_m: Decimal = Field(gt=0, le=10000)
    area_m2: Decimal | None = Field(default=None, gt=0, le=100000000)
    notas: str | None = Field(default=None, max_length=1000)
    fecha_visita_utc: datetime | None = None


class VisitaResponse(VisitaOut):
    etag: str


class TransicionIn(BaseModel):
    estatus_destino: str = Field(min_length=1, max_length=40)
    comentario: str | None = Field(default=None, max_length=1000)


class HistorialItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sitio_id: int
    estatus_anterior: str | None
    estatus_nuevo: str
    tipo: str
    motivo: str | None
    comentario: str | None
    usuario_oid: UUID
    fecha_utc: datetime
    origen: str


class DevolverIn(BaseModel):
    estatus_destino: str = Field(min_length=1, max_length=40)
    motivo: str = Field(min_length=1, max_length=40)
    comentario: str = Field(min_length=5, max_length=1000)


class DescartarIn(BaseModel):
    motivo: str = Field(min_length=1, max_length=40)
    comentario: str = Field(min_length=5, max_length=1000)


class ReasignarIn(BaseModel):
    coordinador_oid: UUID


class EstatusItem(BaseModel):
    codigo: str
    nombre: str
    orden: int
    terminal: bool


class MotivoItem(BaseModel):
    codigo: str
    nombre: str


class TipoDocumentoItem(BaseModel):
    id: str
    nombre: str
    requerido_en_estatus: str | None
    orden: int


class Catalogos(BaseModel):
    estatus: list[EstatusItem]
    motivos_devolucion: list[MotivoItem]
    tipos_documento: list[TipoDocumentoItem]
