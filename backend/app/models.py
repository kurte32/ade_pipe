"""SQLAlchemy models. Shared by every module; owned by the integrator.

Tables follow TDD section 6 plus TO_BE.md section 5 additions. `auditoria` and
`sitio_estatus_historial` are append-only ledger tables created by raw DDL in the baseline
migration (Alembic autogenerate excludes them). RLS predicates apply to every table that
carries `coordinador_oid`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Unicode,
    UnicodeText,
    UniqueConstraint,
)
from sqlalchemy.dialects.mssql import TIMESTAMP, UNIQUEIDENTIFIER
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

LEDGER_TABLES = {"auditoria", "sitio_estatus_historial"}

ESTATUS_PROSPECTADO = "sitio_prospectado"
ESTATUS_DUENO = "dueno_localizado"
ESTATUS_VISITA = "primera_visita"
ESTATUS_DOCUMENTOS = "recepcion_documentos"
ESTATUS_DESCARTADO = "descartado"
ESTATUS_ENTREGADO = "entregado"
ESTATUS_ORDER = [ESTATUS_PROSPECTADO, ESTATUS_DUENO, ESTATUS_VISITA, ESTATUS_DOCUMENTOS]


class Base(DeclarativeBase):
    pass


class Estatus(Base):
    __tablename__ = "estatus"
    codigo: Mapped[str] = mapped_column(Unicode(40), primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(80))
    orden: Mapped[int] = mapped_column(Integer)
    terminal: Mapped[bool] = mapped_column(Boolean, default=False)


class MotivoDevolucion(Base):
    __tablename__ = "motivo_devolucion"
    codigo: Mapped[str] = mapped_column(Unicode(40), primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(120))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CatalogoTipoDocumento(Base):
    __tablename__ = "catalogo_tipo_documento"
    id: Mapped[str] = mapped_column(Unicode(50), primary_key=True)
    nombre: Mapped[str] = mapped_column(Unicode(120))
    requerido_en_estatus: Mapped[str | None] = mapped_column(
        Unicode(40), ForeignKey("estatus.codigo")
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)


class CoordinadorEquivalencia(Base):
    __tablename__ = "coordinador_equivalencia"
    usuario_codigo: Mapped[str] = mapped_column(Unicode(10), primary_key=True)
    correo: Mapped[str] = mapped_column(Unicode(200))
    oid: Mapped[uuid.UUID | None] = mapped_column(UNIQUEIDENTIFIER, nullable=True)
    nombre: Mapped[str | None] = mapped_column(Unicode(200))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    actualizado_por: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER)
    actualizado_utc: Mapped[datetime] = mapped_column(DateTime)


class CargaLote(Base):
    __tablename__ = "carga_lote"
    id: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER, primary_key=True, default=uuid.uuid4)
    archivo_nombre: Mapped[str] = mapped_column(Unicode(260))
    hash: Mapped[str] = mapped_column(CHAR(64))
    usuario_admin: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER)
    fecha_utc: Mapped[datetime] = mapped_column(DateTime)
    filas_total: Mapped[int] = mapped_column(Integer, default=0)
    filas_ok: Mapped[int] = mapped_column(Integer, default=0)
    filas_advertencia: Mapped[int] = mapped_column(Integer, default=0)
    filas_error: Mapped[int] = mapped_column(Integer, default=0)
    estado: Mapped[str] = mapped_column(Unicode(20), default="vista_previa")
    confirmado_utc: Mapped[datetime | None] = mapped_column(DateTime)
    filas_insertadas: Mapped[int | None] = mapped_column(Integer)
    filas_actualizadas: Mapped[int | None] = mapped_column(Integer)
    filas_revision: Mapped[int | None] = mapped_column(Integer)
    filas: Mapped[list[CargaFilaStaging]] = relationship(
        back_populates="lote", cascade="all, delete-orphan"
    )


class CargaFilaStaging(Base):
    __tablename__ = "carga_fila_staging"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lote_id: Mapped[uuid.UUID] = mapped_column(
        UNIQUEIDENTIFIER, ForeignKey("carga_lote.id", ondelete="CASCADE")
    )
    num_fila: Mapped[int] = mapped_column(Integer)
    datos_originales: Mapped[str] = mapped_column(UnicodeText)
    datos_normalizados: Mapped[str | None] = mapped_column(UnicodeText)
    resultado: Mapped[str] = mapped_column(Unicode(15))
    motivos: Mapped[str] = mapped_column(UnicodeText, default="[]")
    decision_admin: Mapped[str | None] = mapped_column(Unicode(10))
    decidido_por: Mapped[uuid.UUID | None] = mapped_column(UNIQUEIDENTIFIER)
    decidido_utc: Mapped[datetime | None] = mapped_column(DateTime)
    origen_id: Mapped[int | None] = mapped_column(Integer)
    accion_prevista: Mapped[str | None] = mapped_column(Unicode(12))
    lote: Mapped[CargaLote] = relationship(back_populates="filas")
    __table_args__ = (Index("ix_carga_fila_lote", "lote_id", "num_fila"),)


class Sitio(Base):
    __tablename__ = "sitio"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    origen_id: Mapped[int] = mapped_column(Integer, unique=True)
    nombre: Mapped[str] = mapped_column(Unicode(200))
    region: Mapped[str] = mapped_column(Unicode(100))
    lat: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    lon: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    gps_texto: Mapped[str | None] = mapped_column(Unicode(50))
    potencial: Mapped[str] = mapped_column(Unicode(20))
    campos_capturados: Mapped[int] = mapped_column(Integer)
    campos_total: Mapped[int] = mapped_column(Integer)
    fecha_origen_utc: Mapped[datetime] = mapped_column(DateTime)
    fecha_origen_texto: Mapped[str] = mapped_column(Unicode(40))
    estatus: Mapped[str] = mapped_column(Unicode(40), ForeignKey("estatus.codigo"))
    coordinador_oid: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER)
    usuario_codigo: Mapped[str] = mapped_column(Unicode(10))
    devuelto: Mapped[bool] = mapped_column(Boolean, default=False)
    devolucion_motivo: Mapped[str | None] = mapped_column(Unicode(40))
    devolucion_comentario: Mapped[str | None] = mapped_column(Unicode(1000))
    en_revision_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    revision_detalle: Mapped[str | None] = mapped_column(Unicode(400))
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)
    carga_lote_id: Mapped[uuid.UUID | None] = mapped_column(
        UNIQUEIDENTIFIER, ForeignKey("carga_lote.id")
    )
    creado_utc: Mapped[datetime] = mapped_column(DateTime)
    actualizado_utc: Mapped[datetime] = mapped_column(DateTime)
    rowversion: Mapped[bytes] = mapped_column(
        TIMESTAMP,
        nullable=False,
        system=True,
        server_default=FetchedValue(),
        server_onupdate=FetchedValue(),
    )

    contacto: Mapped[SitioContacto | None] = relationship(back_populates="sitio", uselist=False)
    visita: Mapped[SitioVisita | None] = relationship(back_populates="sitio", uselist=False)
    archivos: Mapped[list[SitioArchivo]] = relationship(back_populates="sitio")
    __table_args__ = (
        Index("ix_sitio_coordinador", "coordinador_oid", "vigente"),
        Index("ix_sitio_estatus", "estatus"),
    )


class SitioContacto(Base):
    __tablename__ = "sitio_contacto"
    sitio_id: Mapped[int] = mapped_column(Integer, ForeignKey("sitio.id"), primary_key=True)
    coordinador_oid: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER)
    nombre: Mapped[str] = mapped_column(Unicode(200))
    telefono: Mapped[str] = mapped_column(Unicode(30))
    correo: Mapped[str | None] = mapped_column(Unicode(200))
    notas: Mapped[str | None] = mapped_column(Unicode(1000))
    capturado_por: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER)
    capturado_utc: Mapped[datetime] = mapped_column(DateTime)
    sitio: Mapped[Sitio] = relationship(back_populates="contacto")


class SitioVisita(Base):
    __tablename__ = "sitio_visita"
    sitio_id: Mapped[int] = mapped_column(Integer, ForeignKey("sitio.id"), primary_key=True)
    coordinador_oid: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER)
    frente_m: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    fondo_m: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    area_m2: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    notas: Mapped[str | None] = mapped_column(Unicode(1000))
    fecha_visita_utc: Mapped[datetime] = mapped_column(DateTime)
    capturado_por: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER)
    capturado_utc: Mapped[datetime] = mapped_column(DateTime)
    sitio: Mapped[Sitio] = relationship(back_populates="visita")


class SitioArchivo(Base):
    __tablename__ = "sitio_archivo"
    id: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER, primary_key=True, default=uuid.uuid4)
    sitio_id: Mapped[int] = mapped_column(Integer, ForeignKey("sitio.id"))
    coordinador_oid: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER)
    tipo: Mapped[str] = mapped_column(Unicode(10))  # foto | documento
    tipo_documento: Mapped[str | None] = mapped_column(
        Unicode(50), ForeignKey("catalogo_tipo_documento.id")
    )
    nombre_original: Mapped[str] = mapped_column(Unicode(260))
    content_type: Mapped[str] = mapped_column(Unicode(100))
    ruta_blob: Mapped[str] = mapped_column(Unicode(400))
    sha256: Mapped[str] = mapped_column(CHAR(64))
    bytes: Mapped[int] = mapped_column(BigInteger)
    paginas: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)
    estado: Mapped[str] = mapped_column(Unicode(12), default="publicado")  # publicado | purgado
    subido_por: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER)
    subido_utc: Mapped[datetime] = mapped_column(DateTime)
    purga_utc: Mapped[datetime | None] = mapped_column(DateTime)
    purgado_utc: Mapped[datetime | None] = mapped_column(DateTime)
    sitio: Mapped[Sitio] = relationship(back_populates="archivos")
    __table_args__ = (Index("ix_sitio_archivo_sitio", "sitio_id", "tipo", "vigente"),)


class SubidaSesion(Base):
    __tablename__ = "subida_sesion"
    id: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER, primary_key=True, default=uuid.uuid4)
    sitio_id: Mapped[int] = mapped_column(Integer, ForeignKey("sitio.id"))
    coordinador_oid: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER)
    tipo: Mapped[str] = mapped_column(Unicode(10))
    tipo_documento: Mapped[str | None] = mapped_column(Unicode(50))
    nombre_original: Mapped[str] = mapped_column(Unicode(260))
    content_type: Mapped[str] = mapped_column(Unicode(100))
    bytes_total: Mapped[int] = mapped_column(BigInteger)
    tamano_parte: Mapped[int] = mapped_column(Integer)
    partes_total: Mapped[int] = mapped_column(Integer)
    sha256_esperado: Mapped[str] = mapped_column(CHAR(64))
    sha256_real: Mapped[str | None] = mapped_column(CHAR(64))
    estado: Mapped[str] = mapped_column(Unicode(12), default="abierta")
    motivo_rechazo: Mapped[str | None] = mapped_column(Unicode(400))
    blob_staging: Mapped[str] = mapped_column(Unicode(400))
    paginas: Mapped[int | None] = mapped_column(Integer)
    archivo_id: Mapped[uuid.UUID | None] = mapped_column(UNIQUEIDENTIFIER)
    creado_utc: Mapped[datetime] = mapped_column(DateTime)
    actualizado_utc: Mapped[datetime] = mapped_column(DateTime)
    expira_utc: Mapped[datetime] = mapped_column(DateTime)


class NotificacionOutbox(Base):
    __tablename__ = "notificacion_outbox"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sitio_id: Mapped[int] = mapped_column(Integer, ForeignKey("sitio.id"))
    destinatario_oid: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER)
    tipo: Mapped[str] = mapped_column(Unicode(30))
    cuerpo: Mapped[str] = mapped_column(UnicodeText)
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    estado: Mapped[str] = mapped_column(Unicode(12), default="pendiente")
    siguiente_intento_utc: Mapped[datetime] = mapped_column(DateTime)
    enviada_utc: Mapped[datetime | None] = mapped_column(DateTime)
    ultimo_error: Mapped[str | None] = mapped_column(Unicode(400))
    leida_utc: Mapped[datetime | None] = mapped_column(DateTime)
    creado_utc: Mapped[datetime] = mapped_column(DateTime)


class OperacionIdempotente(Base):
    __tablename__ = "operacion_idempotente"
    clave: Mapped[str] = mapped_column(Unicode(80), primary_key=True)
    usuario_oid: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER, primary_key=True)
    ruta: Mapped[str] = mapped_column(Unicode(200))
    hash_cuerpo: Mapped[str] = mapped_column(CHAR(64))
    codigo_respuesta: Mapped[int] = mapped_column(Integer)
    cuerpo_respuesta: Mapped[str] = mapped_column(UnicodeText)
    creado_utc: Mapped[datetime] = mapped_column(DateTime)


# Ledger tables (append-only). Created by raw DDL in the baseline migration.
class SitioEstatusHistorial(Base):
    __tablename__ = "sitio_estatus_historial"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sitio_id: Mapped[int] = mapped_column(Integer)
    estatus_anterior: Mapped[str | None] = mapped_column(Unicode(40))
    estatus_nuevo: Mapped[str] = mapped_column(Unicode(40))
    tipo: Mapped[str] = mapped_column(Unicode(12))  # avance | devolucion | carga | reasignacion
    motivo: Mapped[str | None] = mapped_column(Unicode(40))
    comentario: Mapped[str | None] = mapped_column(Unicode(1000))
    usuario_oid: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER)
    fecha_utc: Mapped[datetime] = mapped_column(DateTime)
    origen: Mapped[str] = mapped_column(Unicode(10))


class Auditoria(Base):
    __tablename__ = "auditoria"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fecha_utc: Mapped[datetime] = mapped_column(DateTime)
    usuario_oid: Mapped[uuid.UUID] = mapped_column(UNIQUEIDENTIFIER)
    rol: Mapped[str] = mapped_column(Unicode(20))
    accion: Mapped[str] = mapped_column(Unicode(60))
    entidad: Mapped[str] = mapped_column(Unicode(40))
    entidad_id: Mapped[str] = mapped_column(Unicode(60))
    ip: Mapped[str | None] = mapped_column(Unicode(45))
    correlation_id: Mapped[str | None] = mapped_column(Unicode(64))
    detalle: Mapped[str | None] = mapped_column(UnicodeText)


__all__ = [
    "Base",
    "Estatus",
    "MotivoDevolucion",
    "CatalogoTipoDocumento",
    "CoordinadorEquivalencia",
    "CargaLote",
    "CargaFilaStaging",
    "Sitio",
    "SitioContacto",
    "SitioVisita",
    "SitioArchivo",
    "SubidaSesion",
    "NotificacionOutbox",
    "OperacionIdempotente",
    "SitioEstatusHistorial",
    "Auditoria",
    "UniqueConstraint",
]
