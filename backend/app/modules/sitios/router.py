from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.security import ROLE_ADMIN, ROLE_COORDINADOR, Claims, require_role
from app.deps import SitioId, get_session
from app.modules.sitios import service
from app.modules.sitios.schemas import SitioDelta, SitioDetail, SitioPage

router = APIRouter(prefix="/api/v1/sitios", tags=["sitios"])
_any_role = require_role(ROLE_COORDINADOR, ROLE_ADMIN)


@router.get("", response_model=SitioPage)
def list_sitios(
    cursor: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    estatus: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    region: str | None = None,
    incluir_no_vigentes: bool = False,
    en_revision_admin: bool | None = Query(
        default=None, description="solo sitios que esperan una decisión del administrador"
    ),
    devuelto: bool | None = Query(default=None, description="solo sitios devueltos"),
    claims: Claims = Depends(_any_role),
    session: Session = Depends(get_session),
) -> SitioPage:
    return service.list_sitios(
        session,
        claims,
        cursor,
        limit,
        estatus,
        q,
        region,
        incluir_no_vigentes,
        en_revision_admin=en_revision_admin,
        devuelto=devuelto,
    )


@router.get("/delta", response_model=SitioDelta)
def delta(
    desde: str | None = Query(default=None, max_length=16),
    conocidos: str | None = Query(
        default=None, description="ids conocidos por el cliente, separados por coma"
    ),
    claims: Claims = Depends(_any_role),
    session: Session = Depends(get_session),
) -> SitioDelta:
    known = [int(x) for x in conocidos.split(",") if x.strip().isdigit()] if conocidos else None
    return SitioDelta.model_validate(service.delta(session, claims, desde, known))


@router.get("/resumen")
def resumen(
    claims: Claims = Depends(_any_role), session: Session = Depends(get_session)
) -> dict[str, int]:
    return service.count_by_estatus(session)


@router.get("/{sitio_id}", response_model=SitioDetail)
def get_sitio(
    sitio_id: SitioId,
    response: Response,
    claims: Claims = Depends(_any_role),
    session: Session = Depends(get_session),
) -> SitioDetail:
    s = service.get_sitio(session, sitio_id)
    response.headers["ETag"] = f'"{service.etag_of(s)}"'
    return service.to_detail(s, claims)
