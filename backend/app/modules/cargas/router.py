from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.core.errors import unprocessable
from app.core.ratelimit import rate_limited
from app.core.security import ROLE_ADMIN, Claims, require_role
from app.deps import get_session
from app.modules.cargas import service
from app.modules.cargas.schemas import ConfirmResult, DecisionIn, LoteDetail, LoteSummary

router = APIRouter(prefix="/api/v1/admin/cargas", tags=["cargas"])
_admin = require_role(ROLE_ADMIN)


@router.post("", response_model=LoteSummary, status_code=201)
async def crear_carga(
    _limit: None = Depends(rate_limited("cargas", "rate_limit_loads_per_minute")),
    file: UploadFile = File(...),
    claims: Claims = Depends(_admin),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> LoteSummary:
    data = await file.read(settings.load_max_bytes + 1)
    if len(data) > settings.load_max_bytes:
        raise unprocessable(
            f"El archivo supera el límite de {settings.load_max_bytes // (1024 * 1024)} MB."
        )
    # Parsing and validation are CPU-bound; keep them off the event loop.
    lote = await run_in_threadpool(
        service.create_lote, session, claims, file.filename or "archivo", data, settings
    )
    return service.to_summary(lote)


@router.get("", response_model=list[LoteSummary])
def listar_cargas(
    limit: int = Query(default=50, ge=1, le=200),
    claims: Claims = Depends(_admin),
    session: Session = Depends(get_session),
) -> list[LoteSummary]:
    return service.list_lotes(session, limit)


@router.get("/{lote_id}", response_model=LoteDetail)
def detalle_carga(
    lote_id: uuid.UUID,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    resultado: str | None = Query(default=None, pattern="^(ok|advertencia|error)$"),
    claims: Claims = Depends(_admin),
    session: Session = Depends(get_session),
) -> LoteDetail:
    lote = service.get_lote(session, lote_id)
    return LoteDetail(
        lote=service.to_summary(lote), filas=service.filas_page(lote, cursor, limit, resultado)
    )


@router.post("/{lote_id}/decisiones", response_model=LoteSummary)
def decidir(
    lote_id: uuid.UUID,
    decisions: list[DecisionIn],
    claims: Claims = Depends(_admin),
    session: Session = Depends(get_session),
) -> LoteSummary:
    return service.decide(session, claims, lote_id, decisions)


@router.post("/{lote_id}/confirmar", response_model=ConfirmResult)
def confirmar(
    lote_id: uuid.UUID,
    claims: Claims = Depends(_admin),
    session: Session = Depends(get_session),
) -> ConfirmResult:
    return service.confirm(session, claims, lote_id)


@router.post("/{lote_id}/cancelar", response_model=LoteSummary)
def cancelar(
    lote_id: uuid.UUID,
    claims: Claims = Depends(_admin),
    session: Session = Depends(get_session),
) -> LoteSummary:
    return service.cancel(session, claims, lote_id)
