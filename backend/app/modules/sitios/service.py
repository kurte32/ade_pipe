from __future__ import annotations

import base64
from typing import Any

from sqlalchemy import func, select, text, true
from sqlalchemy.orm import Session, selectinload

from app.core.errors import not_found, unprocessable
from app.core.security import Claims
from app.models import Sitio
from app.modules.sitios.schemas import ArchivoOut, SitioDetail, SitioListItem, SitioPage

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
# Keep IN-list chunks well under SQL Server's 2100-parameter statement limit (audit B-03).
_ID_CHUNK = 1000


def etag_of(sitio: Sitio) -> str:
    return sitio.rowversion.hex()


def _encode_cursor(sitio_id: int) -> str:
    return base64.urlsafe_b64encode(str(sitio_id).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> int:
    pad = "=" * (-len(cursor) % 4)
    try:
        return int(base64.urlsafe_b64decode(cursor + pad).decode())
    except Exception as exc:  # noqa: BLE001
        raise unprocessable("cursor inválido") from exc


def to_list_item(s: Sitio) -> SitioListItem:
    return SitioListItem.model_validate({**_base_fields(s)})


def _base_fields(s: Sitio) -> dict[str, Any]:
    return {
        "id": s.id,
        "origen_id": s.origen_id,
        "nombre": s.nombre,
        "region": s.region,
        "lat": s.lat,
        "lon": s.lon,
        "potencial": s.potencial,
        "campos_capturados": s.campos_capturados,
        "campos_total": s.campos_total,
        "estatus": s.estatus,
        "devuelto": s.devuelto,
        "usuario_codigo": s.usuario_codigo,
        "en_revision_admin": s.en_revision_admin,
        "vigente": s.vigente,
        "actualizado_utc": s.actualizado_utc,
        "etag": etag_of(s),
    }


def to_detail(s: Sitio, claims: Claims) -> SitioDetail:
    data = _base_fields(s)
    data.update(
        gps_texto=s.gps_texto,
        fecha_origen_utc=s.fecha_origen_utc,
        devolucion_motivo=s.devolucion_motivo,
        devolucion_comentario=s.devolucion_comentario,
        revision_detalle=s.revision_detalle,
        contacto=s.contacto,
        visita=s.visita,
        archivos=[
            ArchivoOut.model_validate({**a.__dict__, "id": str(a.id)})
            for a in sorted(s.archivos, key=lambda a: a.subido_utc)
            if a.estado == "publicado"
        ],
        coordinador_oid=str(s.coordinador_oid) if claims.is_admin else None,
    )
    return SitioDetail.model_validate(data)


def list_sitios(
    session: Session,
    claims: Claims,
    cursor: str | None,
    limit: int | None,
    estatus: str | None,
    q: str | None,
    region: str | None,
    incluir_no_vigentes: bool,
) -> SitioPage:
    lim = min(limit or DEFAULT_LIMIT, MAX_LIMIT)
    stmt = select(Sitio)
    if not incluir_no_vigentes:
        stmt = stmt.where(Sitio.vigente == true())
    if estatus:
        stmt = stmt.where(Sitio.estatus == estatus)
    if region:
        stmt = stmt.where(Sitio.region == region)
    if q:
        stmt = stmt.where(Sitio.nombre.ilike(f"%{q}%"))
    if cursor:
        stmt = stmt.where(Sitio.id > _decode_cursor(cursor))
    stmt = stmt.order_by(Sitio.id).limit(lim + 1)
    rows = list(session.execute(stmt).scalars())
    next_cursor = _encode_cursor(rows[lim - 1].id) if len(rows) > lim else None
    return SitioPage(items=[to_list_item(s) for s in rows[:lim]], next_cursor=next_cursor)


def get_sitio(session: Session, sitio_id: int) -> Sitio:
    s = session.execute(
        select(Sitio)
        .options(
            selectinload(Sitio.contacto), selectinload(Sitio.visita), selectinload(Sitio.archivos)
        )
        .where(Sitio.id == sitio_id)
    ).scalar_one_or_none()
    if s is None:
        raise not_found("Sitio")  # RLS makes foreign sites indistinguishable from missing ones
    return s


def delta(
    session: Session, claims: Claims, desde_hex: str | None, known_ids: list[int] | None
) -> dict[str, Any]:
    """Changes since a rowversion for the offline cache.

    `removed_ids` are ids the client reported as known that are no longer visible to the caller
    (reassigned or no longer vigente). RLS hides reassigned sites, so the client must send its
    known ids to learn what to delete.
    """
    # Watermark: one below the lowest rowversion still held by an open transaction, so changes
    # that commit after this read are picked up by the next delta (MIN_ACTIVE_ROWVERSION is
    # @@DBTS + 1 when nothing is in flight).
    max_rv = (
        session.execute(
            text(
                "SELECT CONVERT(varchar(16), CONVERT(binary(8), "
                "CONVERT(bigint, MIN_ACTIVE_ROWVERSION()) - 1), 2)"
            )
        ).scalar()
        or "0" * 16
    )
    stmt = (
        select(Sitio)
        .options(
            selectinload(Sitio.contacto), selectinload(Sitio.visita), selectinload(Sitio.archivos)
        )
        .where(Sitio.vigente == true())
    )
    if desde_hex:
        try:
            desde = bytes.fromhex(desde_hex)
        except ValueError as exc:
            raise unprocessable("desde debe ser hexadecimal") from exc
        stmt = stmt.where(Sitio.rowversion > desde)
    rows = list(session.execute(stmt.order_by(Sitio.id)).scalars())
    removed: list[int] = []
    if known_ids:
        # Chunk the IN list: SQL Server caps a statement at 2100 parameters, so a coordinator whose
        # offline cache exceeds ~2100 sites would otherwise 500 on every delta sync (audit B-03).
        visible: set[int] = set()
        for start in range(0, len(known_ids), _ID_CHUNK):
            chunk = known_ids[start : start + _ID_CHUNK]
            visible.update(
                session.execute(
                    select(Sitio.id).where(Sitio.id.in_(chunk), Sitio.vigente == true())
                ).scalars()
            )
        removed = sorted(set(known_ids) - visible)
    return {
        "items": [to_detail(s, claims) for s in rows],
        "removed_ids": removed,
        "max_rowversion": max_rv,
    }


def count_by_estatus(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(Sitio.estatus, func.count()).where(Sitio.vigente == true()).group_by(Sitio.estatus)
    ).all()
    return {str(k): int(v) for k, v in rows}
