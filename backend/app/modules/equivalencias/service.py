from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select, true
from sqlalchemy.orm import Session

from app.core.clock import to_utc_naive, utcnow
from app.core.config import get_settings
from app.core.db import system_session
from app.core.errors import unprocessable
from app.core.security import ROLE_ADMIN, Claims
from app.models import CoordinadorEquivalencia
from app.modules.auditoria import service as auditoria
from app.modules.equivalencias.directory import DevDirectory, Directory, get_directory
from app.modules.equivalencias.schemas import EquivalenciaIn, EquivalenciaOut

log = structlog.get_logger()
DEV_COORDINADORES = ("ard", "mmi", "jjt", "jal", "ede", "cmc", "rsp", "usa", "bgl", "jdc")


def to_out(e: CoordinadorEquivalencia) -> EquivalenciaOut:
    return EquivalenciaOut(
        usuario_codigo=e.usuario_codigo,
        correo=e.correo,
        oid=str(e.oid) if e.oid else None,
        nombre=e.nombre,
        activo=e.activo,
        actualizado_utc=e.actualizado_utc,
    )


def list_equivalencias(session: Session) -> list[EquivalenciaOut]:
    rows = session.execute(
        select(CoordinadorEquivalencia).order_by(CoordinadorEquivalencia.usuario_codigo)
    ).scalars()
    return [to_out(e) for e in rows]


def resolve_codigo(session: Session, usuario_codigo: str) -> CoordinadorEquivalencia | None:
    e = session.get(CoordinadorEquivalencia, usuario_codigo.strip().lower())
    if e is None or not e.activo or e.oid is None:
        return None
    return e


def active_map(session: Session) -> dict[str, CoordinadorEquivalencia]:
    rows = session.execute(
        select(CoordinadorEquivalencia).where(
            CoordinadorEquivalencia.activo == true(), CoordinadorEquivalencia.oid.is_not(None)
        )
    ).scalars()
    return {e.usuario_codigo: e for e in rows}


def upsert_many(
    session: Session,
    claims: Claims,
    items: list[EquivalenciaIn],
    directory: Directory | None = None,
) -> list[EquivalenciaOut]:
    """Resolve every email first; reject the whole request if any does not resolve."""
    directory = directory or get_directory()
    seen: set[str] = set()
    errors: list[dict[str, str]] = []
    resolved: dict[str, tuple[uuid.UUID, str]] = {}
    for it in items:
        if it.usuario_codigo in seen:
            errors.append({"usuario_codigo": it.usuario_codigo, "mensaje": "código repetido"})
            continue
        seen.add(it.usuario_codigo)
        try:
            hit = directory.resolve(it.correo)
        except Exception as exc:  # noqa: BLE001 - directory unavailable
            log.warning("directory_error", error=type(exc).__name__)
            raise unprocessable(
                "No fue posible consultar el directorio. Intenta de nuevo.",
                {
                    "errors": [
                        {"usuario_codigo": it.usuario_codigo, "mensaje": "directorio no disponible"}
                    ]
                },
            ) from exc
        if hit is None:
            errors.append(
                {
                    "usuario_codigo": it.usuario_codigo,
                    "mensaje": "el correo no resuelve a una cuenta del directorio",
                }
            )
        else:
            resolved[it.usuario_codigo] = hit
    if errors:
        raise unprocessable(
            "Una o más equivalencias no resuelven a una cuenta.", {"errors": errors}
        )

    now = to_utc_naive(utcnow())
    out: list[EquivalenciaOut] = []
    for it in items:
        oid, nombre = resolved[it.usuario_codigo]
        row = session.get(CoordinadorEquivalencia, it.usuario_codigo)
        old_correo = row.correo if row else None
        old_oid = str(row.oid) if row and row.oid else None
        if row is None:
            row = CoordinadorEquivalencia(usuario_codigo=it.usuario_codigo)
            session.add(row)
        row.correo = it.correo.strip()
        row.oid = oid
        row.nombre = nombre or None
        row.activo = it.activo
        row.actualizado_por = claims.oid
        row.actualizado_utc = now
        auditoria.record(
            session,
            claims,
            "equivalencia_actualizada",
            "coordinador_equivalencia",
            it.usuario_codigo,
            {
                "correo_anterior": old_correo,
                "correo_nuevo": row.correo,
                "oid_anterior": old_oid,
                "oid_nuevo": str(oid),
                "activo": it.activo,
            },
        )
        session.flush()
        out.append(to_out(row))
    return out


def dev_admin_claims(directory: DevDirectory) -> Claims:
    adm = next(u for u in directory.users() if u.get("code") == "adm")
    return Claims(
        oid=uuid.UUID(str(adm["oid"])),
        name=str(adm.get("name", "")),
        username=str(adm.get("email", "")),
        roles=(ROLE_ADMIN,),
        azp="seed",
        tid=get_settings().auth_tenant_id,
    )


def seed_dev_equivalencias() -> None:
    """Upsert the ten coordinator codes from the dev IdP. Local and test only; idempotent."""
    settings = get_settings()
    if settings.directory_mode != "dev":
        log.info("seed_equivalencias_skipped", reason="DIRECTORY_MODE is not dev")
        return
    directory = DevDirectory(settings.dev_idp_url)
    users = {str(u["code"]): u for u in directory.users()}
    items = [
        EquivalenciaIn(usuario_codigo=code, correo=str(users[code]["email"]), activo=True)
        for code in DEV_COORDINADORES
        if code in users
    ]
    claims = dev_admin_claims(directory)
    with system_session() as session:
        upsert_many(session, claims, items, directory)
    log.info("seed_equivalencias_done", count=len(items))
