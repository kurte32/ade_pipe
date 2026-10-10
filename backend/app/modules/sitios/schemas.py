from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ContactoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    nombre: str
    telefono: str
    correo: str | None = None
    notas: str | None = None
    capturado_utc: datetime


class VisitaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    frente_m: Decimal
    fondo_m: Decimal
    area_m2: Decimal | None = None
    notas: str | None = None
    fecha_visita_utc: datetime
    capturado_utc: datetime


class ArchivoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tipo: str
    tipo_documento: str | None = None
    nombre_original: str
    content_type: str
    bytes: int
    paginas: int | None = None
    version: int
    vigente: bool
    estado: str
    subido_utc: datetime


class SitioListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    origen_id: int
    nombre: str
    region: str
    lat: Decimal
    lon: Decimal
    potencial: str
    campos_capturados: int
    campos_total: int
    estatus: str
    devuelto: bool
    usuario_codigo: str
    en_revision_admin: bool
    vigente: bool
    actualizado_utc: datetime
    etag: str


class SitioDetail(SitioListItem):
    gps_texto: str | None = None
    fecha_origen_utc: datetime
    devolucion_motivo: str | None = None
    devolucion_comentario: str | None = None
    contacto: ContactoOut | None = None
    visita: VisitaOut | None = None
    archivos: list[ArchivoOut] = []
    coordinador_oid: str | None = None  # only populated for Admin


class SitioPage(BaseModel):
    items: list[SitioListItem]
    next_cursor: str | None = None


class SitioDelta(BaseModel):
    items: list[SitioDetail]
    removed_ids: list[int]
    max_rowversion: str
