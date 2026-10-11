from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core import idempotency
from app.core.security import ROLE_ADMIN, ROLE_COORDINADOR, Claims, require_role
from app.deps import SitioId, client_ip, get_session, idempotency_key, if_match
from app.modules.sitios.schemas import SitioDetail
from app.modules.transiciones import service
from app.modules.transiciones.schemas import (
    Catalogos,
    ContactoIn,
    ContactoResponse,
    DescartarIn,
    DevolverIn,
    HistorialItem,
    ReasignarIn,
    TransicionIn,
    VisitaIn,
    VisitaResponse,
)

router = APIRouter(tags=["transiciones"])
_coord = require_role(ROLE_COORDINADOR)
_admin = require_role(ROLE_ADMIN)
_any = require_role(ROLE_COORDINADOR, ROLE_ADMIN)


def _with_etag(body: dict[str, Any], status: int = 200) -> JSONResponse:
    resp = JSONResponse(body, status_code=status)
    etag = body.get("etag")
    if etag:
        resp.headers["ETag"] = f'"{etag}"'
    return resp


def _idempotent(
    session: Session,
    claims: Claims,
    key: str | None,
    route: str,
    payload: dict[str, Any],
    work: Any,
    status: int = 200,
) -> JSONResponse:
    body_hash = idempotency.request_hash(payload)
    code, body = idempotency.run_once(
        session,
        claims,
        key,
        route,
        body_hash,
        lambda: (status, work().model_dump(mode="json")),
    )
    return _with_etag(body, code)


# --- coordinator ------------------------------------------------------------------------------


@router.put("/api/v1/sitios/{sitio_id}/contacto", response_model=ContactoResponse)
def put_contacto(
    sitio_id: SitioId,
    data: ContactoIn,
    claims: Claims = Depends(_coord),
    session: Session = Depends(get_session),
    key: str | None = Depends(idempotency_key),
    ip: str | None = Depends(client_ip),
    etag: str | None = Depends(if_match),
) -> JSONResponse:
    return _idempotent(
        session,
        claims,
        key,
        f"PUT /sitios/{sitio_id}/contacto",
        data.model_dump(mode="json"),
        lambda: service.upsert_contacto(session, claims, sitio_id, data, ip, etag),
    )


@router.put("/api/v1/sitios/{sitio_id}/visita", response_model=VisitaResponse)
def put_visita(
    sitio_id: SitioId,
    data: VisitaIn,
    claims: Claims = Depends(_coord),
    session: Session = Depends(get_session),
    key: str | None = Depends(idempotency_key),
    ip: str | None = Depends(client_ip),
    etag: str | None = Depends(if_match),
) -> JSONResponse:
    return _idempotent(
        session,
        claims,
        key,
        f"PUT /sitios/{sitio_id}/visita",
        data.model_dump(mode="json"),
        lambda: service.upsert_visita(session, claims, sitio_id, data, ip, etag),
    )


@router.post("/api/v1/sitios/{sitio_id}/transiciones", response_model=SitioDetail, status_code=201)
def post_transicion(
    sitio_id: SitioId,
    data: TransicionIn,
    claims: Claims = Depends(_coord),
    session: Session = Depends(get_session),
    key: str | None = Depends(idempotency_key),
    etag: str | None = Depends(if_match),
    ip: str | None = Depends(client_ip),
) -> JSONResponse:
    return _idempotent(
        session,
        claims,
        key,
        f"POST /sitios/{sitio_id}/transiciones",
        data.model_dump(mode="json"),
        lambda: service.avanzar(session, claims, sitio_id, data, etag, ip),
        status=201,
    )


@router.get("/api/v1/sitios/{sitio_id}/historial", response_model=list[HistorialItem])
def get_historial(
    sitio_id: SitioId, claims: Claims = Depends(_any), session: Session = Depends(get_session)
) -> list[HistorialItem]:
    return service.historial(session, sitio_id)


@router.get("/api/v1/catalogos", response_model=Catalogos)
def get_catalogos(
    claims: Claims = Depends(_any), session: Session = Depends(get_session)
) -> Catalogos:
    return service.catalogos(session)


# --- admin ------------------------------------------------------------------------------------


@router.post("/api/v1/admin/sitios/{sitio_id}/devolver", response_model=SitioDetail)
def post_devolver(
    sitio_id: SitioId,
    data: DevolverIn,
    response: Response,
    claims: Claims = Depends(_admin),
    session: Session = Depends(get_session),
    etag: str | None = Depends(if_match),
    ip: str | None = Depends(client_ip),
) -> SitioDetail:
    detail = service.devolver(session, claims, sitio_id, data, etag, ip)
    response.headers["ETag"] = f'"{detail.etag}"'
    return detail


@router.post("/api/v1/admin/sitios/{sitio_id}/descartar", response_model=SitioDetail)
def post_descartar(
    sitio_id: SitioId,
    data: DescartarIn,
    response: Response,
    claims: Claims = Depends(_admin),
    session: Session = Depends(get_session),
    etag: str | None = Depends(if_match),
    ip: str | None = Depends(client_ip),
) -> SitioDetail:
    detail = service.descartar(session, claims, sitio_id, data, etag, ip)
    response.headers["ETag"] = f'"{detail.etag}"'
    return detail


@router.post("/api/v1/admin/sitios/{sitio_id}/reasignar", response_model=SitioDetail)
def post_reasignar(
    sitio_id: SitioId,
    data: ReasignarIn,
    response: Response,
    claims: Claims = Depends(_admin),
    session: Session = Depends(get_session),
    etag: str | None = Depends(if_match),
    ip: str | None = Depends(client_ip),
) -> SitioDetail:
    detail = service.reasignar(session, claims, sitio_id, data, etag, ip)
    response.headers["ETag"] = f'"{detail.etag}"'
    return detail
