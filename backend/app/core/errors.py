"""RFC 9457 Problem Details for every error response."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm.exc import StaleDataError

from app.core.logging import current_correlation_id

PROBLEM_BASE = "https://pipeline.tiendas3b/problems/"
log = structlog.get_logger()


class AppError(Exception):
    def __init__(
        self,
        status: int,
        type_slug: str,
        title: str,
        detail: str = "",
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail or title)
        self.status = status
        self.type_slug = type_slug
        self.title = title
        self.detail = detail
        self.extra = extra or {}
        self.headers = headers or {}


def not_found(entity: str = "Recurso") -> AppError:
    return AppError(404, "not-found", "No encontrado", f"{entity} no encontrado")


def precondition_failed(current: dict[str, Any] | None = None) -> AppError:
    return AppError(
        412,
        "precondition-failed",
        "El registro cambió",
        "El registro fue modificado por otra operación. Recarga y vuelve a intentar.",
        {"current": current} if current is not None else {},
    )


def conflict(detail: str, extra: dict[str, Any] | None = None) -> AppError:
    return AppError(409, "conflict", "Conflicto", detail, extra)


def unprocessable(detail: str, extra: dict[str, Any] | None = None) -> AppError:
    return AppError(422, "unprocessable", "Operación no válida", detail, extra)


def _problem(
    request: Request,
    status: int,
    slug: str,
    title: str,
    detail: str,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": PROBLEM_BASE + slug,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": str(request.url.path),
        "correlation_id": current_correlation_id(),
    }
    if extra:
        body.update(extra)
    return JSONResponse(
        body, status_code=status, headers=headers or {}, media_type="application/problem+json"
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return _problem(
            request, exc.status, exc.type_slug, exc.title, exc.detail, exc.extra, exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "loc": [str(x) for x in e.get("loc", [])],
                "msg": e.get("msg", ""),
                "type": e.get("type", ""),
            }
            for e in exc.errors()
        ]
        return _problem(
            request,
            422,
            "validation",
            "Datos inválidos",
            "La petición no cumple el esquema.",
            {"errors": errors},
        )

    @app.exception_handler(StaleDataError)
    async def _stale(request: Request, exc: StaleDataError) -> JSONResponse:
        # The row's rowversion advanced between read and write (concurrent writer); the DB rejected
        # the UPDATE (audit finding B-01). Report the same 412 the explicit If-Match check uses.
        return _problem(
            request,
            412,
            "precondition-failed",
            "El registro cambió",
            "El registro fue modificado por otra operación. Recarga y vuelve a intentar.",
        )

    @app.exception_handler(OperationalError)
    async def _db_unavailable(request: Request, exc: OperationalError) -> JSONResponse:
        # The database could not be reached or the connection dropped (failover, outage): this is
        # a 503 the clients retry with backoff, not an "internal error" (RB-11, backlog SIM).
        log.warning("database_unavailable", route=request.url.path, error=type(exc).__name__)
        return _problem(
            request,
            503,
            "service-unavailable",
            "Servicio no disponible",
            "La base de datos no responde; reintenta en unos segundos.",
            None,
            {"Retry-After": "10"},
        )

    @app.exception_handler(DBAPIError)
    async def _db_error(request: Request, exc: DBAPIError) -> JSONResponse:
        if exc.connection_invalidated:
            return await _db_unavailable(request, OperationalError("", None, exc.orig))  # type: ignore[arg-type]
        log.exception("unhandled_error", route=request.url.path)
        return _problem(
            request,
            500,
            "internal",
            "Error interno",
            "Ocurrió un error inesperado. Reporta el correlation_id.",
        )

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException) -> JSONResponse:
        slug = {
            401: "unauthorized",
            403: "forbidden",
            404: "not-found",
            405: "method-not-allowed",
        }.get(exc.status_code, "http-error")
        return _problem(
            request, exc.status_code, slug, "Error", str(exc.detail), None, dict(exc.headers or {})
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", route=request.url.path)
        return _problem(
            request,
            500,
            "internal",
            "Error interno",
            "Ocurrió un error inesperado. Reporta el correlation_id.",
        )
