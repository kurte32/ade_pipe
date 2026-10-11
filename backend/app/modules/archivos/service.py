"""Upload sessions, validation, scan, promotion, download and purge (TDD 9, TO_BE 6.3)."""

from __future__ import annotations

import hashlib
import tempfile
import uuid
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import func, select, true, update
from sqlalchemy.orm import Session

from app.core.clock import to_utc_naive, utcnow
from app.core.config import Settings
from app.core.errors import AppError, not_found, unprocessable
from app.core.security import Claims
from app.core.storage import BlobStore
from app.models import (
    ESTATUS_DOCUMENTOS,
    CatalogoTipoDocumento,
    Sitio,
    SitioArchivo,
    SubidaSesion,
)
from app.modules.archivos import validation as v
from app.modules.archivos.scan import Scanner
from app.modules.archivos.schemas import ArchivoMeta, SubidaCreate, SubidaOut
from app.modules.auditoria import service as auditoria

log = structlog.get_logger()

ESTADO_ABIERTA = "abierta"
ESTADO_ESCANEANDO = "escaneando"
ESTADO_PUBLICADA = "publicada"
ESTADO_RECHAZADA = "rechazada"
ESTADO_EXPIRADA = "expirada"
ESTADO_CANCELADA = "cancelada"

SYSTEM_OID = uuid.UUID("00000000-0000-0000-0000-000000000000")
SYSTEM_CLAIMS = Claims(
    oid=SYSTEM_OID, name="sistema", username="sistema", roles=("Sistema",), azp="", tid=""
)


def _now() -> Any:
    return to_utc_naive(utcnow())


# --- serialization ---------------------------------------------------------------------------


def subida_out(subida: SubidaSesion, partes: list[int]) -> SubidaOut:
    return SubidaOut(
        id=str(subida.id),
        sitio_id=subida.sitio_id,
        tipo=subida.tipo,
        tipo_documento=subida.tipo_documento,
        estado=subida.estado,
        tamano_parte=subida.tamano_parte,
        partes_total=subida.partes_total,
        partes_recibidas=partes,
        expira_utc=subida.expira_utc,
        motivo_rechazo=subida.motivo_rechazo,
        archivo_id=str(subida.archivo_id) if subida.archivo_id else None,
    )


def archivo_meta(a: SitioArchivo) -> ArchivoMeta:
    return ArchivoMeta.model_validate({**a.__dict__, "id": str(a.id)})


# --- lookups ---------------------------------------------------------------------------------


def get_subida(session: Session, subida_id: uuid.UUID) -> SubidaSesion:
    row = session.get(SubidaSesion, subida_id)
    if row is None:
        raise not_found("Sesión de subida")  # RLS hides foreign sessions
    return row


def get_archivo(session: Session, archivo_id: uuid.UUID) -> SitioArchivo:
    row = session.get(SitioArchivo, archivo_id)
    if row is None:
        raise not_found("Archivo")
    return row


def received_parts(store: BlobStore, subida: SubidaSesion) -> list[int]:
    return sorted(store.uncommitted_blocks(subida.blob_staging))


# --- session lifecycle -----------------------------------------------------------------------


def create_session(
    session: Session, claims: Claims, settings: Settings, body: SubidaCreate
) -> SubidaSesion:
    v.validate_session_request(
        settings, body.tipo, body.content_type, body.bytes_total, body.tipo_documento
    )
    sitio = session.get(Sitio, body.sitio_id)
    if sitio is None:
        raise not_found("Sitio")
    if not sitio.vigente:
        raise unprocessable("El sitio no está vigente")
    if body.tipo == "documento":
        cat = session.get(CatalogoTipoDocumento, body.tipo_documento)
        if cat is None or not cat.activo:
            raise unprocessable("tipo_documento no existe en el catálogo")
    now = _now()
    sid = uuid.uuid4()
    chunk = settings.upload_chunk_bytes
    subida = SubidaSesion(
        id=sid,
        sitio_id=sitio.id,
        coordinador_oid=claims.oid,
        tipo=body.tipo,
        tipo_documento=body.tipo_documento if body.tipo == "documento" else None,
        nombre_original=body.nombre_original,
        content_type=body.content_type,
        bytes_total=body.bytes_total,
        tamano_parte=chunk,
        partes_total=v.parts_for(body.bytes_total, chunk),
        sha256_esperado=body.sha256.lower(),
        estado=ESTADO_ABIERTA,
        blob_staging=v.staging_path(sid, body.nombre_original),
        creado_utc=now,
        actualizado_utc=now,
        expira_utc=now + timedelta(hours=settings.upload_session_ttl_hours),
    )
    session.add(subida)
    session.flush()
    auditoria.record(
        session,
        claims,
        "subida_iniciada",
        "subida_sesion",
        subida.id,
        {"sitio_id": sitio.id, "tipo": subida.tipo, "bytes": subida.bytes_total},
    )
    return subida


def _require_open(subida: SubidaSesion) -> None:
    if subida.estado != ESTADO_ABIERTA:
        raise unprocessable(f"La sesión de subida está en estado '{subida.estado}'")
    if subida.expira_utc < _now():
        raise unprocessable("La sesión de subida expiró; inicia una nueva")


def expected_part_bytes(subida: SubidaSesion, n: int) -> int:
    """Check the session is open and ``n`` in range; return the exact size part ``n`` needs."""
    _require_open(subida)
    if n < 0 or n >= subida.partes_total:
        raise unprocessable(f"Número de parte fuera de rango (0..{subida.partes_total - 1})")
    return v.expected_part_size(n, subida.bytes_total, subida.tamano_parte, subida.partes_total)


def put_part(
    session: Session, store: BlobStore, subida: SubidaSesion, n: int, data: bytes
) -> list[int]:
    expected = expected_part_bytes(subida, n)
    if len(data) != expected:
        raise unprocessable(f"La parte {n} debe tener {expected} bytes y tiene {len(data)}")
    store.stage_block(subida.blob_staging, n, data)
    subida.actualizado_utc = _now()
    return received_parts(store, subida)


def cancel_session(
    session: Session, claims: Claims, store: BlobStore, subida: SubidaSesion
) -> None:
    if subida.estado in (ESTADO_PUBLICADA,):
        raise unprocessable("La sesión ya fue publicada")
    store.delete("staging", subida.blob_staging)
    subida.estado = ESTADO_CANCELADA
    subida.actualizado_utc = _now()
    auditoria.record(session, claims, "subida_cancelada", "subida_sesion", subida.id)


def reject(
    session: Session,
    claims: Claims,
    store: BlobStore,
    subida: SubidaSesion,
    motivo: str,
    accion: str = "subida_rechazada",
) -> None:
    store.delete("staging", subida.blob_staging)
    subida.estado = ESTADO_RECHAZADA
    subida.motivo_rechazo = motivo[:400]
    subida.actualizado_utc = _now()
    auditoria.record(session, claims, accion, "subida_sesion", subida.id, {"motivo": motivo[:400]})


# --- completion: assemble, verify, validate, scan, promote -----------------------------------


def _assemble_and_validate(
    store: BlobStore, settings: Settings, subida: SubidaSesion
) -> tuple[str, int | None]:
    """Commit blocks, stream back verifying the hash and the real type. Returns (sha256, pages)."""
    store.commit_blocks(subida.blob_staging, subida.partes_total, subida.content_type)
    digest = hashlib.sha256()
    head = b""
    size = 0
    with tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024) as tmp:
        for chunk in store.download("staging", subida.blob_staging):
            if len(head) < 64:
                head += chunk[: 64 - len(head)]
            digest.update(chunk)
            size += len(chunk)
            tmp.write(chunk)
        if size != subida.bytes_total:
            raise unprocessable(f"Se recibieron {size} bytes; se esperaban {subida.bytes_total}")
        sha = digest.hexdigest()
        if sha != subida.sha256_esperado:
            raise unprocessable("El hash SHA-256 del archivo no coincide con el anunciado")
        real = v.detect_type(head)
        if real != subida.content_type:
            raise unprocessable("El contenido del archivo no corresponde al tipo declarado")
        pages: int | None = None
        if subida.tipo == "documento":
            tmp.seek(0)
            pages = v.validate_pdf(tmp, settings.pdf_max_pages)
    return sha, pages


def complete(
    session: Session,
    claims: Claims,
    store: BlobStore,
    settings: Settings,
    scanner: Scanner,
    subida: SubidaSesion,
) -> tuple[str, SitioArchivo | None]:
    """Returns ('publicado', archivo) or ('escaneando', None)."""
    if subida.estado == ESTADO_PUBLICADA and subida.archivo_id:
        return "publicado", get_archivo(session, subida.archivo_id)
    if subida.estado == ESTADO_ESCANEANDO:
        return "escaneando", None
    _require_open(subida)
    received = set(received_parts(store, subida))
    missing = sorted(set(range(subida.partes_total)) - received)
    if missing:
        raise unprocessable(f"Faltan {len(missing)} partes", {"partes_faltantes": missing[:50]})
    try:
        sha, pages = _assemble_and_validate(store, settings, subida)
    except AppError as exc:
        # The rejection must survive the 422 response, so commit before re-raising.
        reject(session, claims, store, subida, exc.detail)
        session.commit()
        raise
    subida.sha256_real = sha
    subida.paginas = pages
    result = scanner.result(subida.blob_staging)
    return _apply_scan_result(session, claims, store, settings, subida, result)


def _apply_scan_result(
    session: Session,
    claims: Claims,
    store: BlobStore,
    settings: Settings,
    subida: SubidaSesion,
    result: str,
) -> tuple[str, SitioArchivo | None]:
    if result == "clean":
        return "publicado", promote(session, claims, store, settings, subida)
    if result == "malicious":
        reject(
            session,
            claims,
            store,
            subida,
            "Archivo rechazado por malware",
            "archivo_rechazado_malware",
        )
        session.commit()
        raise unprocessable("El archivo fue identificado como malicioso y se rechazó")
    if result == "pending":
        subida.estado = ESTADO_ESCANEANDO
        subida.actualizado_utc = _now()
        return "escaneando", None
    subida.estado = ESTADO_ESCANEANDO
    subida.actualizado_utc = _now()
    log.error("scan_error", subida_id=str(subida.id))
    return "escaneando", None


def _next_version(session: Session, subida: SubidaSesion) -> int:
    stmt = select(func.max(SitioArchivo.version)).where(
        SitioArchivo.sitio_id == subida.sitio_id, SitioArchivo.tipo == subida.tipo
    )
    if subida.tipo == "documento":
        stmt = stmt.where(SitioArchivo.tipo_documento == subida.tipo_documento)
    current = session.execute(stmt).scalar()
    return int(current or 0) + 1


def promote(
    session: Session, claims: Claims, store: BlobStore, settings: Settings, subida: SubidaSesion
) -> SitioArchivo:
    """Copy the validated staging blob to the documents store and register it. Idempotent."""
    if subida.estado == ESTADO_PUBLICADA and subida.archivo_id:
        return get_archivo(session, subida.archivo_id)
    sha = subida.sha256_real or subida.sha256_esperado
    archivo_id = uuid.uuid4()
    ext = v.extension_for(subida.content_type)
    dst = v.document_path(subida.sitio_id, subida.tipo, archivo_id, sha, ext)
    store.copy_staging_to_documents(subida.blob_staging, dst)
    now = _now()
    if subida.tipo == "documento":
        session.execute(
            update(SitioArchivo)
            .where(
                SitioArchivo.sitio_id == subida.sitio_id,
                SitioArchivo.tipo == "documento",
                SitioArchivo.tipo_documento == subida.tipo_documento,
                SitioArchivo.vigente == true(),
            )
            .values(vigente=False)
        )
    archivo = SitioArchivo(
        id=archivo_id,
        sitio_id=subida.sitio_id,
        coordinador_oid=subida.coordinador_oid,
        tipo=subida.tipo,
        tipo_documento=subida.tipo_documento,
        nombre_original=subida.nombre_original,
        content_type=subida.content_type,
        ruta_blob=dst,
        sha256=sha,
        bytes=subida.bytes_total,
        paginas=subida.paginas,
        version=_next_version(session, subida),
        vigente=True,
        estado="publicado",
        subido_por=subida.coordinador_oid,
        subido_utc=now,
        # Provisional retention start event: upload date (TDD pendiente 7).
        purga_utc=now
        + timedelta(days=365 * settings.retention_years + settings.retention_years // 4),
    )
    session.add(archivo)
    subida.estado = ESTADO_PUBLICADA
    subida.archivo_id = archivo_id
    subida.actualizado_utc = now
    session.flush()
    store.delete("staging", subida.blob_staging)
    auditoria.record(
        session,
        claims,
        "archivo_publicado",
        "sitio_archivo",
        archivo_id,
        {
            "sitio_id": subida.sitio_id,
            "tipo": subida.tipo,
            "tipo_documento": subida.tipo_documento,
            "sha256": sha,
            "bytes": subida.bytes_total,
            "paginas": subida.paginas,
            "version": archivo.version,
        },
    )
    return archivo


# --- files -----------------------------------------------------------------------------------


def record_download(
    session: Session, claims: Claims, archivo: SitioArchivo, ip: str | None
) -> None:
    if archivo.estado == "purgado":
        raise AppError(410, "gone", "Archivo purgado", "El archivo fue purgado por retención.")
    auditoria.record(
        session,
        claims,
        "archivo_descargado",
        "sitio_archivo",
        archivo.id,
        {"sitio_id": archivo.sitio_id, "tipo": archivo.tipo, "bytes": archivo.bytes},
        ip=ip,
    )


def soft_delete(session: Session, claims: Claims, archivo: SitioArchivo) -> None:
    if not archivo.vigente:
        return
    if archivo.tipo == "documento":
        sitio = session.get(Sitio, archivo.sitio_id)
        if sitio is not None and sitio.estatus == ESTATUS_DOCUMENTOS:
            others = session.execute(
                select(func.count())
                .select_from(SitioArchivo)
                .where(
                    SitioArchivo.sitio_id == archivo.sitio_id,
                    SitioArchivo.tipo == "documento",
                    SitioArchivo.tipo_documento == archivo.tipo_documento,
                    SitioArchivo.vigente == true(),
                    SitioArchivo.estado == "publicado",
                    SitioArchivo.id != archivo.id,
                )
            ).scalar()
            if not others:
                raise unprocessable(
                    "No se puede retirar el único documento vigente de este tipo "
                    "cuando el sitio ya está en Recepción de documentos"
                )
    archivo.vigente = False
    auditoria.record(
        session,
        claims,
        "archivo_retirado",
        "sitio_archivo",
        archivo.id,
        {"sitio_id": archivo.sitio_id},
    )
