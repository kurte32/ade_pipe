"""Shared fixtures.

Integration tests use the live compose stack: the dev IdP mints real RS256 tokens, the API
validates them against the IdP's JWKS, and the database is the SQL Server container with RLS.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.clock import to_utc_naive, utcnow

DEV_IDP = os.environ.get("DEV_IDP_URL", "http://localhost:8001").rstrip("/")
PWA_CLIENT_ID = "33333333-3333-4333-8333-333333333333"
ADMIN_CLIENT_ID = "44444444-4444-4444-8444-444444444444"


def mint(user_code: str, client_id: str = PWA_CLIENT_ID, scope: str = "access_as_user") -> str:
    r = httpx.post(
        f"{DEV_IDP}/token",
        json={"user_code": user_code, "client_id": client_id, "scope": scope},
        timeout=10,
    )
    r.raise_for_status()
    return str(r.json()["access_token"])


def auth(user_code: str, client_id: str = PWA_CLIENT_ID) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint(user_code, client_id)}"}


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def dev_users() -> dict[str, dict[str, object]]:
    r = httpx.get(f"{DEV_IDP}/users", timeout=10)
    r.raise_for_status()
    return {str(u["code"]): u for u in r.json()}


@pytest.fixture(scope="session")
def coord_a_headers() -> dict[str, str]:
    return auth("ard")


@pytest.fixture(scope="session")
def coord_b_headers() -> dict[str, str]:
    return auth("usa")


@pytest.fixture(scope="session")
def admin_headers() -> dict[str, str]:
    return auth("adm", ADMIN_CLIENT_ID)


def make_sitio(
    session,
    *,
    coordinador_oid: uuid.UUID,
    usuario_codigo: str,
    origen_id: int | None = None,
    **over,
):  # type: ignore[no-untyped-def]
    """Insert a site directly (test setup only). Needs an Admin or Sistema session context."""
    from app.models import ESTATUS_PROSPECTADO, Sitio

    now = to_utc_naive(utcnow())
    s = Sitio(
        origen_id=origen_id or int(str(uuid.uuid4().int)[:8]),
        nombre=over.get("nombre", f"Sitio prueba {uuid.uuid4().hex[:6]}"),
        region=over.get("region", "Xalapa"),
        lat=Decimal("19.530000"),
        lon=Decimal("-96.920000"),
        gps_texto=None,
        potencial="Sin estatus",
        campos_capturados=4,
        campos_total=24,
        fecha_origen_utc=now - timedelta(days=1),
        fecha_origen_texto="10/08/2026 14:37:02",
        estatus=over.get("estatus", ESTATUS_PROSPECTADO),
        coordinador_oid=coordinador_oid,
        usuario_codigo=usuario_codigo,
        creado_utc=now,
        actualizado_utc=now,
    )
    session.add(s)
    session.flush()
    return s


@pytest.fixture
def two_sites(dev_users):  # type: ignore[no-untyped-def]
    """One site for coordinator A (ard) and one for coordinator B (usa), inserted as Sistema."""
    from app.core.db import system_session

    oid_a = uuid.UUID(str(dev_users["ard"]["oid"]))
    oid_b = uuid.UUID(str(dev_users["usa"]["oid"]))
    with system_session() as s:
        a = make_sitio(s, coordinador_oid=oid_a, usuario_codigo="ard")
        b = make_sitio(s, coordinador_oid=oid_b, usuario_codigo="usa", region="Azcapotzalco")
        ids = (a.id, b.id)
    yield {"a": ids[0], "b": ids[1], "oid_a": oid_a, "oid_b": oid_b}
    with system_session() as s:
        for t in (
            "sitio_contacto",
            "sitio_visita",
            "sitio_archivo",
            "subida_sesion",
            "notificacion_outbox",
        ):
            s.execute(
                text(f"DELETE FROM {t} WHERE sitio_id IN (:a, :b)"),  # noqa: S608
                {"a": ids[0], "b": ids[1]},
            )
        s.execute(text("DELETE FROM sitio WHERE id IN (:a, :b)"), {"a": ids[0], "b": ids[1]})
