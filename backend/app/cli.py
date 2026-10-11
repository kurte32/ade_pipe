"""Operational commands: db-init, seed, openapi.

python -m app.cli db-init   create database, least-privilege login/user (local and test)
python -m app.cli seed      equivalences for dev users + sample bulk load through the real service
python -m app.cli openapi   print the OpenAPI document
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import structlog
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import build_engine
from app.core.logging import configure_logging

log = structlog.get_logger()


def db_init() -> None:
    settings = get_settings()
    if settings.db_auth == "entra":
        # Azure: the database exists (Bicep). Running as the migration identity (Entra admin),
        # create the contained user for the API managed identity so the baseline migration can
        # add it to pipeline_app_role. Idempotent.
        user = settings.db_user
        engine = build_engine(settings)
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(
                text(  # noqa: S608
                    f"IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'{user}') "
                    f"CREATE USER [{user}] FROM EXTERNAL PROVIDER"
                )
            )
        log.info("db_init_done", database=settings.db_name, app_user=user, auth="entra")
        return
    master = build_engine(settings, admin=True, database="master")
    for _ in range(60):
        try:
            with master.connect() as conn:
                conn.execute(text("SELECT 1"))
            break
        except Exception:  # noqa: BLE001
            time.sleep(2)
    else:
        print("database not reachable", file=sys.stderr)
        sys.exit(1)
    # Identifiers come from validated settings, never from request input.
    db, user = settings.db_name, settings.db_user
    pwd = settings.db_password.replace("'", "''")
    with master.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"IF DB_ID(N'{db}') IS NULL CREATE DATABASE [{db}]"))  # noqa: S608
        conn.execute(
            text(  # noqa: S608
                f"IF NOT EXISTS (SELECT 1 FROM sys.sql_logins WHERE name = N'{user}') "
                f"CREATE LOGIN [{user}] WITH PASSWORD = N'{pwd}', CHECK_POLICY = OFF"
            )
        )
    app_db = build_engine(settings, admin=True)
    with app_db.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(
            text(  # noqa: S608
                f"IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'{user}') "
                f"CREATE USER [{user}] FOR LOGIN [{user}]"
            )
        )
    log.info("db_init_done", database=settings.db_name, app_user=settings.db_user)


def seed() -> None:
    from app.modules.cargas.service import seed_sample  # implemented by the cargas module
    from app.modules.equivalencias.service import seed_dev_equivalencias

    seed_dev_equivalencias()
    seed_sample()
    log.info("seed_done")


# Origen ids reserved for end-to-end tests (admin.cargas loads and the provisioned site pool).
E2E_ORIGEN_RANGE = (800_000, 900_000)


def e2e_cleanup() -> None:
    """Remove every site in the e2e id range, its child rows and blobs (audit C7).

    The append-only ledger rows (auditoria, sitio_estatus_historial) stay, by design. Refuses to
    run in production.
    """
    if get_settings().environment == "production":
        raise SystemExit("e2e-cleanup refuses to run in production")
    from app.core.db import system_session
    from app.core.storage import get_blob_store

    lo, hi = E2E_ORIGEN_RANGE
    store = get_blob_store()
    documents: list[str] = []
    staging: list[str] = []
    with system_session() as s:
        ids = [
            int(i)
            for i in s.execute(
                text("SELECT id FROM sitio WHERE origen_id >= :lo AND origen_id < :hi"),
                {"lo": lo, "hi": hi},
            ).scalars()
        ]
        for start in range(0, len(ids), 1000):
            id_list = ",".join(str(i) for i in ids[start : start + 1000])
            documents += list(
                s.execute(
                    text(f"SELECT ruta_blob FROM sitio_archivo WHERE sitio_id IN ({id_list})")
                ).scalars()
            )
            staging += list(
                s.execute(
                    text(f"SELECT blob_staging FROM subida_sesion WHERE sitio_id IN ({id_list})")
                ).scalars()
            )
            for table in (
                "sitio_contacto",
                "sitio_visita",
                "sitio_archivo",
                "subida_sesion",
                "notificacion_outbox",
            ):
                s.execute(text(f"DELETE FROM {table} WHERE sitio_id IN ({id_list})"))
            s.execute(text(f"DELETE FROM sitio WHERE id IN ({id_list})"))
    for path in documents:
        store.delete("documents", path)
    for path in staging:
        store.delete("staging", path)
    log.info("e2e_cleanup_done", sitios=len(ids), documentos=len(documents))


def openapi() -> None:
    from app.main import app

    print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))


def main() -> None:
    configure_logging(get_settings().log_level)
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["db-init", "seed", "openapi", "e2e-cleanup"])
    args = parser.parse_args()
    {"db-init": db_init, "seed": seed, "openapi": openapi, "e2e-cleanup": e2e_cleanup}[
        args.command
    ]()


if __name__ == "__main__":
    main()
