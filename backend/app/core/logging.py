"""Structured JSON logging with correlation ids. No personal data is ever logged."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
import time
import uuid
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

CORRELATION_HEADER = "X-Correlation-Id"
_SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]")
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


_REVISION = os.environ.get("CONTAINER_APP_REVISION", "")


def _add_revision(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    # Container Apps sets CONTAINER_APP_REVISION; one field tells which revision wrote the line.
    if _REVISION:
        event_dict.setdefault("revision", _REVISION)
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        format="%(message)s", stream=sys.stderr, level=getattr(logging, level.upper(), logging.INFO)
    )
    # httpx logs every request URL at INFO: Graph lookups carry emails and oids (audit IDN-4).
    for noisy in ("azure", "urllib3", "uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _drop_forbidden,
            _add_revision,
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
        # The correlation id is always generated here: it is written to the append-only audit
        # ledger, so a client must not be able to choose it (audit A5). A client-sent value is kept
        # only as a sanitized log field so support can still match a device's own reference.
        cid = uuid.uuid4().hex
        started = time.perf_counter()
        token = _correlation_id.set(cid)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=cid, route=request.url.path, method=request.method
        )
        client_cid = _SAFE_ID.sub("", request.headers.get(CORRELATION_HEADER, ""))[:64]
        if client_cid:
            structlog.contextvars.bind_contextvars(client_correlation_id=client_cid)
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
        # Entity ids from the route (backlog LOG-FIELDS): support can filter by site or lot.
        fields: dict[str, object] = {
            k: v
            for k, v in (request.scope.get("path_params") or {}).items()
            if k in ("sitio_id", "lote_id", "archivo_id", "subida_id")
        }
        fields["duration_ms"] = round((time.perf_counter() - started) * 1000)
        if claims is not None:
            fields["user"] = hash_oid(claims.oid)
        structlog.get_logger().info("request", status=response.status_code, **fields)
        return response
