"""Status transitions, captures, admin returns, reassignment (TDD 7, ADR-005)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, true
from sqlalchemy.orm import Session

from app.core.clock import to_utc_naive, utcnow
from app.core.errors import AppError, precondition_failed, unprocessable
from app.core.security import Claims
from app.models import (
    ESTATUS_DESCARTADO,
    ESTATUS_DOCUMENTOS,
    ESTATUS_ORDER,
    CatalogoTipoDocumento,
    CoordinadorEquivalencia,
    Estatus,
    MotivoDevolucion,
    Sitio,
    SitioContacto,
    SitioEstatusHistorial,
    SitioVisita,
)
from app.modules.auditoria import service as auditoria
from app.modules.notificaciones import service as notificaciones
from app.modules.sitios import service as sitios
from app.modules.sitios.schemas import SitioDetail
from app.modules.transiciones import rules
from app.modules.transiciones.schemas import (
    Catalogos,
    ContactoIn,
    ContactoResponse,
    DescartarIn,
    DevolverIn,
    EstatusItem,
    HistorialItem,
    MotivoItem,
    ReasignarIn,
    TipoDocumentoItem,
    TransicionIn,
    VisitaIn,
    VisitaResponse,
)


def _now() -> Any:
    return to_utc_naive(utcnow())


def _touch(sitio: Sitio) -> None:
    """Any update to the row bumps rowversion; this keeps actualizado_utc honest too."""
    sitio.actualizado_utc = _now()


def _require_if_match(sitio: Sitio, if_match: str | None, claims: Claims) -> None:
    if not if_match:
        raise AppError(
            428,
            "precondition-required",
            "Falta If-Match",
            "Envía el ETag del registro en el encabezado If-Match.",
        )
    if if_match.lower() != sitios.etag_of(sitio).lower():
        raise precondition_failed(sitios.to_detail(sitio, claims).model_dump(mode="json"))


def _history(
    session: Session,
    sitio: Sitio,
    anterior: str | None,
    nuevo: str,
    tipo: str,
    claims: Claims,
    origen: str,
    motivo: str | None = None,
    comentario: str | None = None,
) -> None:
    session.add(
        SitioEstatusHistorial(
            sitio_id=sitio.id,
            estatus_anterior=anterior,
            estatus_nuevo=nuevo,
            tipo=tipo,
            motivo=motivo,
            comentario=comentario,
            usuario_oid=claims.oid,
            fecha_utc=_now(),
            origen=origen,
        )
    )


def _refresh(session: Session, sitio: Sitio) -> Sitio:
    session.flush()
    session.refresh(sitio)
    return sitio


def _required_docs(session: Session) -> list[str]:
    return list(
        session.execute(
            select(CatalogoTipoDocumento.id)
            .where(
                CatalogoTipoDocumento.activo == true(),
                CatalogoTipoDocumento.requerido_en_estatus == ESTATUS_DOCUMENTOS,
            )
            .order_by(CatalogoTipoDocumento.orden)
        ).scalars()
    )


def _estatus_nombre(session: Session, codigo: str) -> str:
    row = session.get(Estatus, codigo)
    return row.nombre if row else codigo


# --- captures -----------------------------------------------------------------------------


def _optional_if_match(sitio: Sitio, if_match: str | None, claims: Claims) -> None:
    """Captures are unconditional by default (offline devices rarely hold a fresh ETag), but a
    client that does send If-Match gets the stale-write protection it asked for (audit DAT-9)."""
    if if_match is not None:
        _require_if_match(sitio, if_match, claims)


def upsert_contacto(
    session: Session,
    claims: Claims,
    sitio_id: int,
    data: ContactoIn,
    ip: str | None,
    if_match: str | None = None,
) -> ContactoResponse:
    sitio = sitios.get_sitio(session, sitio_id)
    if sitio.estatus not in ESTATUS_ORDER:
        raise unprocessable("El sitio está en un estatus terminal")
    _optional_if_match(sitio, if_match, claims)
    now = _now()
    c = sitio.contacto
    if c is None:
        c = SitioContacto(
            sitio_id=sitio.id,
            coordinador_oid=sitio.coordinador_oid,
            capturado_por=claims.oid,
            capturado_utc=now,
            nombre=data.nombre,
            telefono=data.telefono,
            correo=data.correo,
            notas=data.notas,
        )
        session.add(c)
        sitio.contacto = c
    else:
        c.nombre = data.nombre
        c.telefono = data.telefono
        c.correo = data.correo
        c.notas = data.notas
        c.capturado_por = claims.oid
        c.capturado_utc = now
    _touch(sitio)
    auditoria.record(session, claims, "contacto_capturado", "sitio", sitio.id, None, ip)
    _refresh(session, sitio)
    return ContactoResponse(
        nombre=c.nombre,
        telefono=c.telefono,
        correo=c.correo,
        notas=c.notas,
        capturado_utc=c.capturado_utc,
        etag=sitios.etag_of(sitio),
    )


def upsert_visita(
    session: Session,
    claims: Claims,
    sitio_id: int,
    data: VisitaIn,
    ip: str | None,
    if_match: str | None = None,
) -> VisitaResponse:
    sitio = sitios.get_sitio(session, sitio_id)
    if sitio.estatus not in ESTATUS_ORDER:
        raise unprocessable("El sitio está en un estatus terminal")
    _optional_if_match(sitio, if_match, claims)
    now = _now()
    fecha = to_utc_naive(data.fecha_visita_utc) if data.fecha_visita_utc else now
    v = sitio.visita
    if v is None:
        v = SitioVisita(
            sitio_id=sitio.id,
            coordinador_oid=sitio.coordinador_oid,
            frente_m=data.frente_m,
            fondo_m=data.fondo_m,
            area_m2=data.area_m2,
            notas=data.notas,
            fecha_visita_utc=fecha,
            capturado_por=claims.oid,
            capturado_utc=now,
        )
        session.add(v)
        sitio.visita = v
    else:
        v.frente_m = data.frente_m
        v.fondo_m = data.fondo_m
        v.area_m2 = data.area_m2
        v.notas = data.notas
        v.fecha_visita_utc = fecha
        v.capturado_por = claims.oid
        v.capturado_utc = now
    _touch(sitio)
    auditoria.record(session, claims, "visita_capturada", "sitio", sitio.id, None, ip)
    _refresh(session, sitio)
    return VisitaResponse(
        frente_m=v.frente_m,
        fondo_m=v.fondo_m,
        area_m2=v.area_m2,
        notas=v.notas,
        fecha_visita_utc=v.fecha_visita_utc,
        capturado_utc=v.capturado_utc,
        etag=sitios.etag_of(sitio),
    )


# --- coordinator transition -------------------------------------------------------------------


def avanzar(
    session: Session,
    claims: Claims,
    sitio_id: int,
    data: TransicionIn,
    if_match: str | None,
    ip: str | None,
) -> SitioDetail:
    sitio = sitios.get_sitio(session, sitio_id)
    destino = data.estatus_destino

    if destino == ESTATUS_DESCARTADO:
        if sitio.estatus not in ESTATUS_ORDER:
            # A proposal on a terminal site would park it in admin review forever (audit DAT-6).
            raise unprocessable("El sitio está en un estatus terminal")
        if not (data.comentario or "").strip():
            raise unprocessable("Indica el motivo para proponer el descarte")
        _require_if_match(sitio, if_match, claims)
        sitio.en_revision_admin = True
        sitio.revision_detalle = f"Propuesta de descarte: {data.comentario.strip()[:360]}"  # type: ignore[union-attr]
        _touch(sitio)
        auditoria.record(
            session, claims, "descarte_propuesto", "sitio", sitio.id, {"comentario": True}, ip
        )
        _refresh(session, sitio)
        return sitios.to_detail(sitio, claims)

    if destino not in ESTATUS_ORDER:
        raise unprocessable("Estatus destino no permitido para el coordinador")
    _require_if_match(sitio, if_match, claims)
    siguiente = rules.next_estatus(sitio.estatus)
    if siguiente is None:
        raise unprocessable("El sitio está en un estatus terminal o final")
    if destino != siguiente:
        raise unprocessable(
            "Solo se puede avanzar un estatus a la vez",
            {"estatus_actual": sitio.estatus, "estatus_siguiente": siguiente},
        )
    # Hold the row while the requirements are evaluated so a concurrent document delete cannot
    # slip between the check and the commit (audit DAT-2); file writes lock the same row.
    session.execute(
        select(Sitio).where(Sitio.id == sitio.id).with_hint(Sitio, "WITH (UPDLOCK, ROWLOCK)")
    ).scalar_one()
    session.refresh(sitio)
    faltantes = rules.check(destino, sitio, _required_docs(session))
    if faltantes:
        raise unprocessable(
            "No se cumplen los requisitos de la transición", {"faltantes": faltantes}
        )

    anterior = sitio.estatus
    sitio.estatus = destino
    sitio.devuelto = False
    sitio.devolucion_motivo = None
    sitio.devolucion_comentario = None
    _touch(sitio)
    _history(session, sitio, anterior, destino, "avance", claims, "pwa", None, data.comentario)
    auditoria.record(
        session, claims, "transicion", "sitio", sitio.id, {"de": anterior, "a": destino}, ip
    )
    _refresh(session, sitio)
    return sitios.to_detail(sitio, claims)


def historial(session: Session, sitio_id: int) -> list[HistorialItem]:
    sitios.get_sitio(session, sitio_id)  # visibility through RLS
    rows = list(
        session.execute(
            select(SitioEstatusHistorial)
            .where(SitioEstatusHistorial.sitio_id == sitio_id)
            .order_by(SitioEstatusHistorial.id.desc())
        ).scalars()
    )
    return [HistorialItem.model_validate(r) for r in rows]


# --- admin -----------------------------------------------------------------------------------


def _motivo(session: Session, codigo: str) -> MotivoDevolucion:
    m = session.get(MotivoDevolucion, codigo)
    if m is None or not m.activo:
        raise unprocessable("Motivo de devolución no válido")
    return m


def devolver(
    session: Session,
    claims: Claims,
    sitio_id: int,
    data: DevolverIn,
    if_match: str | None,
    ip: str | None,
) -> SitioDetail:
    sitio = sitios.get_sitio(session, sitio_id)
    _require_if_match(sitio, if_match, claims)
    if sitio.estatus not in ESTATUS_ORDER:
        raise unprocessable("El sitio está en un estatus terminal")
    if data.estatus_destino not in ESTATUS_ORDER:
        raise unprocessable("Estatus destino no válido")
    if ESTATUS_ORDER.index(data.estatus_destino) >= ESTATUS_ORDER.index(sitio.estatus):
        raise unprocessable("Solo se puede devolver a un estatus anterior")
    motivo = _motivo(session, data.motivo)
    anterior = sitio.estatus
    sitio.estatus = data.estatus_destino
    sitio.devuelto = True
    sitio.devolucion_motivo = motivo.codigo
    sitio.devolucion_comentario = data.comentario.strip()
    sitio.en_revision_admin = False
    sitio.revision_detalle = None
    _touch(sitio)
    _history(
        session,
        sitio,
        anterior,
        data.estatus_destino,
        "devolucion",
        claims,
        "admin",
        motivo.codigo,
        data.comentario.strip(),
    )
    notificaciones.enqueue_devolucion(
        session,
        sitio,
        motivo.codigo,
        motivo.nombre,
        data.estatus_destino,
        _estatus_nombre(session, data.estatus_destino),
        data.comentario.strip(),
    )
    auditoria.record(
        session,
        claims,
        "devolucion",
        "sitio",
        sitio.id,
        {"de": anterior, "a": data.estatus_destino, "motivo": motivo.codigo},
        ip,
    )
    _refresh(session, sitio)
    return sitios.to_detail(sitio, claims)


def descartar(
    session: Session,
    claims: Claims,
    sitio_id: int,
    data: DescartarIn,
    if_match: str | None,
    ip: str | None,
) -> SitioDetail:
    sitio = sitios.get_sitio(session, sitio_id)
    _require_if_match(sitio, if_match, claims)
    if sitio.estatus not in ESTATUS_ORDER:
        raise unprocessable("El sitio ya está en un estatus terminal")
    motivo = _motivo(session, data.motivo)
    anterior = sitio.estatus
    sitio.estatus = ESTATUS_DESCARTADO
    sitio.en_revision_admin = False
    sitio.revision_detalle = None
    _touch(sitio)
    _history(
        session,
        sitio,
        anterior,
        ESTATUS_DESCARTADO,
        "descarte",
        claims,
        "admin",
        motivo.codigo,
        data.comentario.strip(),
    )
    auditoria.record(
        session,
        claims,
        "descarte",
        "sitio",
        sitio.id,
        {"de": anterior, "motivo": motivo.codigo},
        ip,
    )
    _refresh(session, sitio)
    return sitios.to_detail(sitio, claims)


def reasignar(
    session: Session,
    claims: Claims,
    sitio_id: int,
    data: ReasignarIn,
    if_match: str | None,
    ip: str | None,
) -> SitioDetail:
    sitio = sitios.get_sitio(session, sitio_id)
    _require_if_match(sitio, if_match, claims)
    nuevo: UUID = data.coordinador_oid
    if nuevo == sitio.coordinador_oid:
        raise unprocessable("El sitio ya está asignado a ese coordinador")
    anterior_oid = sitio.coordinador_oid
    equiv = session.execute(
        select(CoordinadorEquivalencia).where(
            CoordinadorEquivalencia.oid == nuevo, CoordinadorEquivalencia.activo == true()
        )
    ).scalar_one_or_none()
    if equiv is None:
        # Assigning an oid nobody maps to would make the site invisible to every coordinator and
        # leave usuario_codigo stale, so the next bulk load could never repair it (audit DAT-4).
        raise unprocessable("El coordinador destino no tiene una equivalencia activa")
    sitios.cambiar_propietario(session, sitio, nuevo)
    sitio.usuario_codigo = equiv.usuario_codigo
    sitio.en_revision_admin = False
    sitio.revision_detalle = None
    _touch(sitio)
    _history(
        session,
        sitio,
        sitio.estatus,
        sitio.estatus,
        "reasignacion",
        claims,
        "admin",
        None,
        f"de {anterior_oid} a {nuevo}",
    )
    auditoria.record(
        session,
        claims,
        "reasignacion",
        "sitio",
        sitio.id,
        {"de": str(anterior_oid), "a": str(nuevo)},
        ip,
    )
    session.flush()
    session.expire_all()
    sitio = sitios.get_sitio(session, sitio_id)
    return sitios.to_detail(sitio, claims)


# --- catalogs --------------------------------------------------------------------------------


def catalogos(session: Session) -> Catalogos:
    est = list(session.execute(select(Estatus).order_by(Estatus.orden)).scalars())
    mot = list(
        session.execute(
            select(MotivoDevolucion)
            .where(MotivoDevolucion.activo == true())
            .order_by(MotivoDevolucion.codigo)
        ).scalars()
    )
    tipos = list(
        session.execute(
            select(CatalogoTipoDocumento)
            .where(CatalogoTipoDocumento.activo == true())
            .order_by(CatalogoTipoDocumento.orden)
        ).scalars()
    )
    return Catalogos(
        estatus=[
            EstatusItem(codigo=e.codigo, nombre=e.nombre, orden=e.orden, terminal=e.terminal)
            for e in est
        ],
        motivos_devolucion=[MotivoItem(codigo=m.codigo, nombre=m.nombre) for m in mot],
        tipos_documento=[
            TipoDocumentoItem(
                id=t.id, nombre=t.nombre, requerido_en_estatus=t.requerido_en_estatus, orden=t.orden
            )
            for t in tipos
        ],
    )
