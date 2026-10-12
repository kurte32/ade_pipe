"""FastAPI application factory. Router registration lives here (integrator-owned)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.edge import FrontDoorMiddleware
from app.core.errors import register_error_handlers
from app.core.limits import BodyLimitMiddleware
from app.core.logging import CorrelationMiddleware, configure_logging
from app.core.security import ROLE_ADMIN, Claims, require_role
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


def _schema_versions() -> tuple[str | None, frozenset[str]]:
    """Head revision of the migrations shipped with this code, and every revision in its history."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        here = Path(__file__).resolve().parent.parent
        script = ScriptDirectory.from_config(Config(str(here / "alembic.ini")))
        head = script.get_current_head()
        history = frozenset(r.revision for r in script.walk_revisions())
        return head, history
    except Exception as exc:  # noqa: BLE001 - never block start-up over this
        log.warning("schema_versions_unavailable", error=type(exc).__name__)
        return None, frozenset()


CODE_SCHEMA_HEAD, CODE_SCHEMA_HISTORY = _schema_versions()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Pipeline de Posibles Tiendas API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.deployed else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.deployed else "/api/openapi.json",
    )
    app.add_middleware(CorrelationMiddleware)
    if settings.cors_origins:
        # Only for environments where the SPAs are not served from the API's origin (no Front
        # Door, audit INF-2). Explicit allowlist, bearer tokens only, no credentials.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"],
            allow_headers=["authorization", "content-type", "if-match", "idempotency-key"],
            expose_headers=["etag", "x-correlation-id", "content-disposition"],
            max_age=600,
        )
    if settings.front_door_id:
        app.add_middleware(FrontDoorMiddleware, front_door_id=settings.front_door_id)
    # Added last so it runs first: oversized bodies never reach the app (audit B-05).
    app.add_middleware(BodyLimitMiddleware, limit=settings.max_request_bytes)
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
                # Which schema revision this database carries versus the one this code expects
                # (backlog D-03r). A database behind the code is a deployment that skipped the
                # migrate job; ahead is normal during a rollout (expand-and-contract).
                applied = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            checks["database"] = "ok"
            checks["schema_revision"] = applied
            checks["schema_head"] = CODE_SCHEMA_HEAD
            if applied != CODE_SCHEMA_HEAD:
                checks["schema"] = (
                    "behind" if applied in CODE_SCHEMA_HISTORY else "ahead-or-unknown"
                )
                if checks["schema"] == "behind":
                    ok = False
                    log.warning("schema_behind_code", applied=applied, head=CODE_SCHEMA_HEAD)
            else:
                checks["schema"] = "ok"
        except Exception as exc:  # noqa: BLE001
            ok = False
            checks["database"] = "error"
            log.warning("readiness_check_failed", check="database", error=type(exc).__name__)
        try:
            checks["storage"] = "ok" if get_blob_store().ping() else "missing containers"
            ok = ok and checks["storage"] == "ok"
        except Exception as exc:  # noqa: BLE001
            ok = False
            checks["storage"] = "error"
            log.warning("readiness_check_failed", check="storage", error=type(exc).__name__)
        checks["status"] = "ok" if ok else "degraded"
        if not ok:
            from fastapi import HTTPException

            raise HTTPException(503, detail=checks)
        return checks

    @app.get("/healthz/deps", tags=["health"], include_in_schema=False)
    def healthz_deps(_: Claims = Depends(require_role(ROLE_ADMIN))) -> dict[str, object]:
        """Dependency reachability for an administrator (backlog HEALTH-DEPS): database, storage,
        the token signing keys and Microsoft Graph when it is in use. Never used by probes."""
        import time

        import httpx

        out: dict[str, object] = {}

        def timed(name: str, fn: object) -> None:
            t = time.perf_counter()
            try:
                fn()  # type: ignore[operator]
                out[name] = {"status": "ok", "ms": round((time.perf_counter() - t) * 1000)}
            except Exception as exc:  # noqa: BLE001 - reported, never raised
                out[name] = {"status": "error", "error": type(exc).__name__}

        def db() -> None:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))

        def storage() -> None:
            if not get_blob_store().ping():
                raise RuntimeError("missing containers")

        def jwks() -> None:
            httpx.get(settings.auth_jwks_url, timeout=5).raise_for_status()

        def graph() -> None:
            httpx.get(f"{settings.graph_base_url}/$metadata", timeout=5).raise_for_status()

        timed("database", db)
        timed("storage", storage)
        timed("jwks", jwks)
        if settings.notify_mode == "graph" or settings.directory_mode == "graph":
            timed("graph", graph)
        else:
            out["graph"] = {"status": "skipped", "reason": "not in use"}
        checks = [v for v in out.values() if isinstance(v, dict)]
        out["status"] = (
            "ok" if all(v.get("status") in ("ok", "skipped") for v in checks) else "degraded"
        )
        return out

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
