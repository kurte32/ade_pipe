"""HU-05: equivalences with directory resolution and audit."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import text

from app.core.db import system_session
from tests.conftest import DEV_IDP

pytestmark = pytest.mark.integration


def test_put_resolves_oid_and_audits(client, admin_headers) -> None:  # type: ignore[no-untyped-def]
    users = {u["code"]: u for u in httpx.get(f"{DEV_IDP}/users", timeout=5).json()}
    body = [{"usuario_codigo": "mmi", "correo": users["mmi"]["email"].upper(), "activo": True}]
    r = client.put("/api/v1/admin/equivalencias", headers=admin_headers, json=body)
    assert r.status_code == 200, r.text
    row = r.json()[0]
    assert row["oid"] == users["mmi"]["oid"] and row["nombre"] == users["mmi"]["name"]
    listed = client.get("/api/v1/admin/equivalencias", headers=admin_headers).json()
    assert any(e["usuario_codigo"] == "mmi" and e["oid"] == users["mmi"]["oid"] for e in listed)
    with system_session() as s:
        n = s.execute(
            text(
                "SELECT COUNT(*) FROM auditoria WHERE accion = 'equivalencia_actualizada' "
                "AND entidad_id = 'mmi'"
            )
        ).scalar()
    assert n and n >= 1


def test_unresolved_email_rejects_whole_request(client, admin_headers) -> None:  # type: ignore[no-untyped-def]
    users = {u["code"]: u for u in httpx.get(f"{DEV_IDP}/users", timeout=5).json()}
    body = [
        {"usuario_codigo": "jjt", "correo": users["jjt"]["email"]},
        {"usuario_codigo": "qqq", "correo": "nadie@dev.tiendas3b.test"},
    ]
    r = client.put("/api/v1/admin/equivalencias", headers=admin_headers, json=body)
    assert r.status_code == 422
    assert r.json()["errors"][0]["usuario_codigo"] == "qqq"
    listed = client.get("/api/v1/admin/equivalencias", headers=admin_headers).json()
    assert not any(e["usuario_codigo"] == "qqq" for e in listed)


def test_single_put_and_validation(client, admin_headers) -> None:  # type: ignore[no-untyped-def]
    users = {u["code"]: u for u in httpx.get(f"{DEV_IDP}/users", timeout=5).json()}
    r = client.put(
        "/api/v1/admin/equivalencias/jal",
        headers=admin_headers,
        json={"correo": users["jal"]["email"], "activo": False},
    )
    assert r.status_code == 200 and r.json()["activo"] is False
    try:
        r = client.put(
            "/api/v1/admin/equivalencias/J1", headers=admin_headers, json={"correo": "a@b.c"}
        )
        assert r.status_code == 422
        r = client.put(
            "/api/v1/admin/equivalencias",
            headers=admin_headers,
            json=[{"usuario_codigo": "abc", "correo": "no-es-correo"}],
        )
        assert r.status_code == 422
    finally:
        # restore jal as active for other suites, even when an assertion above fails (TST-3)
        client.put(
            "/api/v1/admin/equivalencias/jal",
            headers=admin_headers,
            json={"correo": users["jal"]["email"], "activo": True},
        )


def test_coordinator_forbidden(client, coord_a_headers) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/api/v1/admin/equivalencias", headers=coord_a_headers).status_code == 403
    assert (
        client.put("/api/v1/admin/equivalencias", headers=coord_a_headers, json=[]).status_code
        == 403
    )
