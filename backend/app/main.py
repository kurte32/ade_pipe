"""FastAPI application factory. Router registration lives here (integrator-owned)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.errors import register_error_handlers
from app.core.logging import CorrelationMiddleware, configure_logging
from app.core.storage import get_blob_store
from app.core.telemetry import configure_telemetry

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info(
        "startup",
        environment=settings.environment,
        auth_mode=settings.auth_mode,
        storage_mode=settings.storage_mode,
    )
    if settings.storage_mode == "azurite":
        get_blob_store().ensure_containers()
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Pipeline de Posibles Tiendas API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.environment != "production" else None,
    )
    app.add_middleware(CorrelationMiddleware)
    register_error_handlers(app)
    configure_telemetry(app, settings)

    @app.get("/healthz", tags=["health"], include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"], include_in_schema=False)
    def readyz() -> dict[str, object]:
        checks: dict[str, object] = {}
        ok = True
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:  # noqa: BLE001
            ok = False
            checks["database"] = f"error: {type(exc).__name__}"
        try:
            checks["storage"] = "ok" if get_blob_store().ping() else "missing containers"
            ok = ok and checks["storage"] == "ok"
        except Exception as exc:  # noqa: BLE001
            ok = False
            checks["storage"] = f"error: {type(exc).__name__}"
        checks["status"] = "ok" if ok else "degraded"
        if not ok:
            from fastapi import HTTPException

            raise HTTPException(503, detail=checks)
        return checks

    _register_routers(app)
    return app


def _register_routers(app: FastAPI) -> None:
    from app.modules.identity.router import router as identity_router
    from app.modules.sitios.router import router as sitios_router

    app.include_router(identity_router)
    app.include_router(sitios_router)
    for modname in (
        "transiciones",
        "cargas",
        "archivos",
        "notificaciones",
        "auditoria",
        "equivalencias",
    ):
        try:
            mod = __import__(f"app.modules.{modname}.router", fromlist=["router"])
        except ModuleNotFoundError:
            log.warning("router_missing", module=modname)
            continue
        app.include_router(mod.router)


app = create_app()
