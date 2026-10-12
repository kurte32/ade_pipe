"""Database engine, sessions, and per-request SESSION_CONTEXT for Row-Level Security.

Local: SQL authentication against the SQL Server container with the least-privilege app login.
Azure: Entra access token from the managed identity, injected into the ODBC connection.
Both use the same engine and the same session-context hooks.
"""

from __future__ import annotations

import struct
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.security import Claims

SQL_COPT_SS_ACCESS_TOKEN = 1256  # ODBC attribute for Entra access tokens
SYSTEM_OID = "00000000-0000-0000-0000-000000000000"


def _odbc_url(settings: Settings, *, admin: bool = False, database: str | None = None) -> str:
    db = database or settings.db_name
    driver = "ODBC Driver 18 for SQL Server"
    encrypt = "yes"
    # Only the compose stack (self-signed SQL Server) may skip certificate validation (IDN-2).
    trust = "no" if settings.deployed else "yes"
    query = f"driver={quote_plus(driver)}&Encrypt={encrypt}&TrustServerCertificate={trust}"
    if settings.db_auth == "entra" and not admin:
        return f"mssql+pyodbc://@{settings.db_host}:{settings.db_port}/{db}?{query}"
    user = settings.db_admin_user if admin else settings.db_user
    password = settings.db_admin_password if admin else settings.db_password
    return (
        f"mssql+pyodbc://{quote_plus(user)}:{quote_plus(password)}@"
        f"{settings.db_host}:{settings.db_port}/{db}?{query}"
    )


def _entra_token_struct() -> bytes:
    from azure.identity import DefaultAzureCredential

    token = DefaultAzureCredential().get_token("https://database.windows.net/.default").token
    raw = token.encode("utf-16-le")
    return struct.pack(f"<I{len(raw)}s", len(raw), raw)


def build_engine(settings: Settings, *, admin: bool = False, database: str | None = None) -> Engine:
    engine = create_engine(
        _odbc_url(settings, admin=admin, database=database),
        pool_pre_ping=True,
        # Bound parameters (owner names, phones) must never reach exception text and logs (IDN-3).
        hide_parameters=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        fast_executemany=True,
        future=True,
    )

    if settings.db_auth == "entra" and not admin:

        @event.listens_for(engine, "do_connect")
        def _inject_token(dialect: Any, conn_rec: Any, cargs: Any, cparams: dict[str, Any]) -> None:
            cparams["attrs_before"] = {SQL_COPT_SS_ACCESS_TOKEN: _entra_token_struct()}

    @event.listens_for(engine, "checkin")
    def _clear_context_on_checkin(dbapi_conn: Any, conn_rec: Any) -> None:
        # Defensive: never let one request's identity leak to the next through the pool.
        try:
            cur = dbapi_conn.cursor()
            cur.execute("EXEC sp_set_session_context @key=N'oid', @value=NULL;")
            cur.execute("EXEC sp_set_session_context @key=N'rol', @value=NULL;")
            cur.close()
        except Exception:  # noqa: BLE001 - connection may be invalid; pool will discard it
            conn_rec.invalidate()

    return engine


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        _engine = build_engine(get_settings())
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


def set_session_context(session: Session, oid: str, rol: str) -> None:
    session.execute(text("EXEC sp_set_session_context @key=N'oid', @value=:oid"), {"oid": oid})
    session.execute(text("EXEC sp_set_session_context @key=N'rol', @value=:rol"), {"rol": rol})


def clear_session_context(session: Session) -> None:
    session.execute(text("EXEC sp_set_session_context @key=N'oid', @value=NULL"))
    session.execute(text("EXEC sp_set_session_context @key=N'rol', @value=NULL"))


@contextmanager
def session_for(claims: Claims, *, role: str | None = None) -> Iterator[Session]:
    """Session whose connection carries the caller's oid and role for RLS."""
    session = session_factory()()
    try:
        set_session_context(session, str(claims.oid), role or claims.primary_role)
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        try:
            clear_session_context(session)
        finally:
            session.close()


@contextmanager
def system_session() -> Iterator[Session]:
    """Session for background jobs. Role 'Sistema' passes the RLS predicate."""
    session = session_factory()()
    try:
        set_session_context(session, SYSTEM_OID, "Sistema")
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        try:
            clear_session_context(session)
        finally:
            session.close()


def iter_session_for(claims: Claims) -> Generator[Session, None, None]:
    with session_for(claims) as s:
        yield s
