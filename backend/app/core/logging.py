"""Structured JSON logging with correlation ids. No personal data is ever logged."""

from __future__ import annotations

import hashlib
import logging
import sys
import uuid
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

CORRELATION_HEADER = "X-Correlation-Id"
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")

FORBIDDEN_KEYS = {
    "nombre",
    "telefono",
    "correo",
    "name",
    "phone",
    "email",
    "token",
    "authorization",
    "password",
    "body",
}


def current_correlation_id() -> str:
    return _correlation_id.get()


def hash_oid(oid: object) -> str:
    return hashlib.sha256(str(oid).encode()).hexdigest()[:16]


def _drop_forbidden(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for k in list(event_dict):
        if k.lower() in FORBIDDEN_KEYS:
            event_dict[k] = "[redacted]"
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        format="%(message)s", stream=sys.stderr, level=getattr(logging, level.upper(), logging.INFO)
    )
    for noisy in ("azure", "urllib3", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _drop_forbidden,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(sys.stderr),
        cache_logger_on_first_use=True,
    )


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cid = request.headers.get(CORRELATION_HEADER) or uuid.uuid4().hex
        cid = cid[:64]
        token = _correlation_id.set(cid)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=cid, route=request.url.path, method=request.method
        )
        request.state.correlation_id = cid
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 - last line of defence keeps the correlation id
            structlog.get_logger().exception("unhandled_error", route=request.url.path)
            response = JSONResponse(
                {
                    "type": "https://pipeline.tiendas3b/problems/internal",
                    "title": "Error interno",
                    "status": 500,
                    "detail": "Ocurrió un error inesperado. Reporta el correlation_id.",
                    "instance": str(request.url.path),
                    "correlation_id": cid,
                },
                status_code=500,
                media_type="application/problem+json",
            )
        finally:
            _correlation_id.reset(token)
        response.headers[CORRELATION_HEADER] = cid
        claims = getattr(request.state, "claims", None)
        if claims is not None:
            structlog.get_logger().info(
                "request", status=response.status_code, user=hash_oid(claims.oid)
            )
        else:
            structlog.get_logger().info("request", status=response.status_code)
        return response
