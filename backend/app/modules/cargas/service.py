"""Bulk load: preview, admin decisions, single-transaction confirm, reload semantics (TDD 8)."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import to_utc_naive, utcnow
from app.core.config import Settings, get_settings
from app.core.db import system_session
from app.core.errors import conflict, not_found, unprocessable
from app.core.security import Claims
from app.models import (
    ESTATUS_PROSPECTADO,
    CargaFilaStaging,
    CargaLote,
    Sitio,
    SitioEstatusHistorial,
)
from app.modules.auditoria import service as auditoria
from app.modules.cargas.parser import parse_upload
from app.modules.cargas.schemas import (
    ConfirmResult,
    DecisionIn,
    FilaOut,
    FilasPage,
    LoteSummary,
)
from app.modules.cargas.validation import (
    ACCION_ACTUALIZAR,
    ACCION_INSERTAR,
    ACCION_REVISION,
    RESULT_ERROR,
    RESULT_OK,
    RESULT_WARNING,
    EquivalenciaRef,
    ExistingSite,
    MissingColumnsError,
    validate_rows,
)
from app.modules.equivalencias import service as equivalencias

log = structlog.get_logger()

ESTADO_PREVIA = "vista_previa"
ESTADO_CONFIRMADO = "confirmado"
ESTADO_CANCELADO = "cancelado"
DEFAULT_SEED_PATH = "/app/samples/pipeline_nacional_mx_20261009_SINTETICO.xlsx"


def _pending_decisions(lote: CargaLote) -> int:
    return sum(1 for f in lote.filas if f.resultado == RESULT_WARNING and f.decision_admin is None)


def to_summary(lote: CargaLote) -> LoteSummary:
    return LoteSummary(
        id=str(lote.id),
        archivo_nombre=lote.archivo_nombre,
        hash=lote.hash,
        fecha_utc=lote.fecha_utc,
        filas_total=lote.filas_total,
        filas_ok=lote.filas_ok,
        filas_advertencia=lote.filas_advertencia,
        filas_error=lote.filas_error,
        estado=lote.estado,
        confirmado_utc=lote.confirmado_utc,
        filas_insertadas=lote.filas_insertadas,
        filas_actualizadas=lote.filas_actualizadas,
        filas_revision=lote.filas_revision,
        pendientes_decision=_pending_decisions(lote) if lote.estado == ESTADO_PREVIA else 0,
    )


def to_fila(f: CargaFilaStaging) -> FilaOut:
    return FilaOut(
        num_fila=f.num_fila,
        resultado=f.resultado,
        motivos=json.loads(f.motivos or "[]"),
        decision_admin=f.decision_admin,
        origen_id=f.origen_id,
        accion_prevista=f.accion_prevista,
        datos=json.loads(f.datos_originales or "{}"),
        normalizado=json.loads(f.datos_normalizados) if f.datos_normalizados else None,
    )


def get_lote(session: Session, lote_id: uuid.UUID) -> CargaLote:
    lote = session.get(CargaLote, lote_id)
    if lote is None:
        raise not_found("Lote de carga")
    return lote


def list_lotes(session: Session, limit: int = 50) -> list[LoteSummary]:
    rows = session.execute(
        select(CargaLote).order_by(CargaLote.fecha_utc.desc()).limit(limit)
    ).scalars()
    return [to_summary(lote) for lote in rows]


def filas_page(lote: CargaLote, cursor: str | None, limit: int, resultado: str | None) -> FilasPage:
    start = int(cursor) if cursor and cursor.isdigit() else 0
    filas = sorted(lote.filas, key=lambda f: f.num_fila)
    if resultado:
        filas = [f for f in filas if f.resultado == resultado]
    filas = [f for f in filas if f.num_fila > start]
    page = filas[:limit]
    next_cursor = str(page[-1].num_fila) if len(filas) > limit and page else None
    return FilasPage(items=[to_fila(f) for f in page], next_cursor=next_cursor)


def _existing_lookup(
    session: Session, origen_ids: list[int]
) -> tuple[dict[int, ExistingSite], list[tuple[int, float, float]]]:
    existing: dict[int, ExistingSite] = {}
    if origen_ids:
        for s in session.execute(select(Sitio).where(Sitio.origen_id.in_(origen_ids))).scalars():
            existing[s.origen_id] = ExistingSite(
                id=s.id,
                origen_id=s.origen_id,
                estatus=s.estatus,
                usuario_codigo=s.usuario_codigo,
                region=s.region,
                nombre=s.nombre,
                lat=float(s.lat),
                lon=float(s.lon),
            )
    coords = [
        (int(i), float(la), float(lo))
        for i, la, lo in session.execute(select(Sitio.id, Sitio.lat, Sitio.lon)).all()
    ]
    return existing, coords


def create_lote(
    session: Session, claims: Claims, filename: str, data: bytes, settings: Settings | None = None
) -> CargaLote:
    settings = settings or get_settings()
    parsed = parse_upload(filename, data, settings)
    eq_map = {
        code: EquivalenciaRef(usuario_codigo=code, oid=e.oid)  # type: ignore[arg-type]
        for code, e in equivalencias.active_map(session).items()
    }
    candidate_ids = [int(v) for r in parsed.rows if (v := (r.get("#") or "").strip()).isdigit()]
    existing, coords = _existing_lookup(session, candidate_ids)
    try:
        results = validate_rows(
            parsed.columns,
            parsed.rows,
            settings,
            equivalencias=eq_map,
            existing=existing,
            existing_coords=coords,
        )
    except MissingColumnsError as exc:
        raise unprocessable(
            f"Faltan columnas requeridas: {', '.join(exc.missing)}.", {"missing": exc.missing}
        ) from exc

    now = to_utc_naive(utcnow())
    lote = CargaLote(
        id=uuid.uuid4(),
        archivo_nombre=Path(filename).name[:260],
        hash=hashlib.sha256(data).hexdigest(),
        usuario_admin=claims.oid,
        fecha_utc=now,
        filas_total=len(results),
        filas_ok=sum(1 for r in results if r.resultado == RESULT_OK),
        filas_advertencia=sum(1 for r in results if r.resultado == RESULT_WARNING),
        filas_error=sum(1 for r in results if r.resultado == RESULT_ERROR),
        estado=ESTADO_PREVIA,
    )
    session.add(lote)
    for r in results:
        lote.filas.append(
            CargaFilaStaging(
                num_fila=r.num_fila,
                datos_originales=json.dumps(r.originales, ensure_ascii=False),
                datos_normalizados=json.dumps(r.normalizado, ensure_ascii=False)
                if r.normalizado
                else None,
                resultado=r.resultado,
                motivos=json.dumps(r.motivos, ensure_ascii=False),
                origen_id=r.origen_id,
                accion_prevista=r.accion_prevista,
            )
        )
    session.flush()
    auditoria.record(
        session,
        claims,
        "carga_creada",
        "carga_lote",
        lote.id,
        {
            "archivo": lote.archivo_nombre,
            "formato": parsed.formato,
            "hash": lote.hash,
            "filas_total": lote.filas_total,
            "filas_ok": lote.filas_ok,
            "filas_advertencia": lote.filas_advertencia,
            "filas_error": lote.filas_error,
        },
    )
    return lote


def decide(
    session: Session, claims: Claims, lote_id: uuid.UUID, decisions: list[DecisionIn]
) -> LoteSummary:
    lote = get_lote(session, lote_id)
    if lote.estado != ESTADO_PREVIA:
        raise conflict("El lote ya no está en vista previa.")
    by_row = {f.num_fila: f for f in lote.filas}
    bad: list[dict[str, Any]] = []
    for d in decisions:
        f = by_row.get(d.num_fila)
        if f is None:
            bad.append({"num_fila": d.num_fila, "mensaje": "fila inexistente"})
        elif f.resultado != RESULT_WARNING:
            bad.append(
                {
                    "num_fila": d.num_fila,
                    "mensaje": "solo las filas con advertencia admiten decisión",
                }
            )
    if bad:
        raise unprocessable("Decisiones no válidas.", {"errors": bad})
    now = to_utc_naive(utcnow())
    for d in decisions:
        f = by_row[d.num_fila]
        f.decision_admin = d.decision
        f.decidido_por = claims.oid
        f.decidido_utc = now
    auditoria.record(
        session,
        claims,
        "carga_decision",
        "carga_lote",
        lote.id,
        {
            "aprobadas": [d.num_fila for d in decisions if d.decision == "aprobar"],
            "excluidas": [d.num_fila for d in decisions if d.decision == "excluir"],
        },
    )
    session.flush()
    return to_summary(lote)


def _apply_update(s: Sitio, n: dict[str, Any], now: datetime) -> None:
    s.nombre = n["nombre"]
    s.region = n["region"]
    s.lat = Decimal(n["lat"])
    s.lon = Decimal(n["lon"])
    s.gps_texto = n.get("gps_texto")
    s.potencial = n["potencial"]
    s.campos_capturados = int(n["campos_capturados"])
    s.campos_total = int(n["campos_total"])
    s.fecha_origen_utc = datetime.fromisoformat(n["fecha_origen_utc"])
    s.fecha_origen_texto = n["fecha_origen_texto"]
    s.actualizado_utc = now


def confirm(session: Session, claims: Claims, lote_id: uuid.UUID) -> ConfirmResult:
    lote = get_lote(session, lote_id)
    if lote.estado == ESTADO_CONFIRMADO:
        raise conflict("El lote ya fue confirmado.")
    if lote.estado != ESTADO_PREVIA:
        raise conflict("El lote fue cancelado.")
    pending = sorted(
        f.num_fila for f in lote.filas if f.resultado == RESULT_WARNING and f.decision_admin is None
    )
    if pending:
        raise unprocessable(
            "Hay filas con advertencia sin decisión.", {"filas_pendientes": pending}
        )

    now = to_utc_naive(utcnow())
    inserted = updated = revision = 0
    origen_ids = [f.origen_id for f in lote.filas if f.origen_id is not None]
    existing = (
        {
            s.origen_id: s
            for s in session.execute(select(Sitio).where(Sitio.origen_id.in_(origen_ids))).scalars()
        }
        if origen_ids
        else {}
    )

    for f in sorted(lote.filas, key=lambda x: x.num_fila):
        if f.resultado == RESULT_ERROR:
            continue
        if f.resultado == RESULT_WARNING and f.decision_admin != "aprobar":
            continue
        n = json.loads(f.datos_normalizados or "{}")
        prev = existing.get(f.origen_id) if f.origen_id is not None else None
        if f.accion_prevista == ACCION_INSERTAR or prev is None:
            if prev is not None:  # created between preview and confirm: treat as update
                _apply_update(prev, n, now)
                updated += 1
                continue
            s = Sitio(
                origen_id=int(n["origen_id"]),
                nombre=n["nombre"],
                region=n["region"],
                lat=Decimal(n["lat"]),
                lon=Decimal(n["lon"]),
                gps_texto=n.get("gps_texto"),
                potencial=n["potencial"],
                campos_capturados=int(n["campos_capturados"]),
                campos_total=int(n["campos_total"]),
                fecha_origen_utc=datetime.fromisoformat(n["fecha_origen_utc"]),
                fecha_origen_texto=n["fecha_origen_texto"],
                estatus=ESTATUS_PROSPECTADO,
                coordinador_oid=uuid.UUID(n["coordinador_oid"]),
                usuario_codigo=n["usuario_codigo"],
                carga_lote_id=lote.id,
                creado_utc=now,
                actualizado_utc=now,
            )
            session.add(s)
            session.flush()
            session.add(
                SitioEstatusHistorial(
                    sitio_id=s.id,
                    estatus_anterior=None,
                    estatus_nuevo=ESTATUS_PROSPECTADO,
                    tipo="carga",
                    usuario_oid=claims.oid,
                    fecha_utc=now,
                    origen="carga",
                )
            )
            inserted += 1
        elif f.accion_prevista == ACCION_REVISION:
            _apply_update(prev, n, now)
            prev.en_revision_admin = True
            prev.revision_detalle = (
                f"Carga {str(lote.id)[:8]} fila {f.num_fila}: USUARIO '{prev.usuario_codigo}' → "
                f"'{n['usuario_codigo']}' en sitio con estatus {prev.estatus}."
            )[:400]
            revision += 1
        else:  # ACCION_ACTUALIZAR
            reassigned = n["usuario_codigo"] != prev.usuario_codigo
            _apply_update(prev, n, now)
            if reassigned and prev.estatus == ESTATUS_PROSPECTADO:
                old = prev.usuario_codigo
                prev.usuario_codigo = n["usuario_codigo"]
                prev.coordinador_oid = uuid.UUID(n["coordinador_oid"])
                session.add(
                    SitioEstatusHistorial(
                        sitio_id=prev.id,
                        estatus_anterior=prev.estatus,
                        estatus_nuevo=prev.estatus,
                        tipo="reasignacion",
                        comentario=f"USUARIO {old} → {prev.usuario_codigo} por carga",
                        usuario_oid=claims.oid,
                        fecha_utc=now,
                        origen="carga",
                    )
                )
            updated += 1
        assert f.accion_prevista in (ACCION_INSERTAR, ACCION_ACTUALIZAR, ACCION_REVISION, None)

    lote.estado = ESTADO_CONFIRMADO
    lote.confirmado_utc = now
    lote.filas_insertadas = inserted
    lote.filas_actualizadas = updated
    lote.filas_revision = revision
    auditoria.record(
        session,
        claims,
        "carga_confirmada",
        "carga_lote",
        lote.id,
        {"insertadas": inserted, "actualizadas": updated, "revision": revision},
    )
    session.flush()
    return ConfirmResult(
        lote=to_summary(lote), insertadas=inserted, actualizadas=updated, revision=revision
    )


def cancel(session: Session, claims: Claims, lote_id: uuid.UUID) -> LoteSummary:
    lote = get_lote(session, lote_id)
    if lote.estado != ESTADO_PREVIA:
        raise conflict("Solo se puede cancelar un lote en vista previa.")
    lote.estado = ESTADO_CANCELADO
    auditoria.record(session, claims, "carga_cancelada", "carga_lote", lote.id)
    session.flush()
    return to_summary(lote)


def seed_sample() -> None:
    """Load the synthetic sample through the real bulk-load path if the pipeline is empty."""
    settings = get_settings()
    path = Path(os.environ.get("SEED_SAMPLE_PATH", DEFAULT_SEED_PATH))
    if not path.exists():
        log.warning("seed_sample_missing", path=str(path))
        return
    from app.modules.equivalencias.directory import DevDirectory

    claims = equivalencias.dev_admin_claims(DevDirectory(settings.dev_idp_url))
    with system_session() as session:
        if (session.execute(select(func.count()).select_from(Sitio)).scalar() or 0) > 0:
            log.info("seed_sample_skipped", reason="sitios already exist")
            return
        lote = create_lote(session, claims, path.name, path.read_bytes(), settings)
        decisions = [
            DecisionIn(num_fila=f.num_fila, decision="aprobar")
            for f in lote.filas
            if f.resultado == RESULT_WARNING
        ]
        if decisions:
            decide(session, claims, lote.id, decisions)
        result = confirm(session, claims, lote.id)
    log.info(
        "seed_sample_done",
        insertadas=result.insertadas,
        actualizadas=result.actualizadas,
        errores=lote.filas_error,
    )
