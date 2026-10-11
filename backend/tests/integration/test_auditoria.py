"""HU-15: audit log viewer (admin only) backed by the append-only ledger."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

CONTACTO = {"nombre": "Luz", "telefono": "5511111111"}


def test_auditoria_forbidden_for_coordinator(client, coord_a_headers):  # type: ignore[no-untyped-def]
    assert client.get("/api/v1/admin/auditoria", headers=coord_a_headers).status_code == 403


def test_auditoria_lists_actions_with_filters(client, admin_headers, coord_a_headers, two_sites):  # type: ignore[no-untyped-def]
    sid = two_sites["a"]
    r = client.put(
        f"/api/v1/sitios/{sid}/contacto",
        json=CONTACTO,
        headers={**coord_a_headers, "X-Correlation-Id": "test-corr-123"},
    )
    assert r.status_code == 200
    contacto_cid = r.headers["X-Correlation-Id"]  # server-issued; the client value is not stored
    r = client.post(
        f"/api/v1/sitios/{sid}/transiciones",
        json={"estatus_destino": "dueno_localizado"},
        headers={**coord_a_headers, "If-Match": f'"{r.json()["etag"]}"'},
    )
    assert r.status_code == 201
    page = client.get(
        f"/api/v1/admin/auditoria?entidad=sitio&entidad_id={sid}", headers=admin_headers
    ).json()
    acciones = [i["accion"] for i in page["items"]]
    assert acciones[:2] == ["transicion", "contacto_capturado"]
    assert page["items"][0]["detalle"] == {"de": "sitio_prospectado", "a": "dueno_localizado"}
    assert page["items"][1]["correlation_id"] == contacto_cid
    assert page["items"][0]["usuario_oid"] == str(two_sites["oid_a"])
    # filter by accion and user
    only = client.get(
        f"/api/v1/admin/auditoria?accion=transicion&usuario_oid={two_sites['oid_a']}",
        headers=admin_headers,
    ).json()
    assert only["items"] and all(i["accion"] == "transicion" for i in only["items"])
    # pagination
    first = client.get("/api/v1/admin/auditoria?limit=1", headers=admin_headers).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = client.get(
        f"/api/v1/admin/auditoria?limit=1&cursor={first['next_cursor']}", headers=admin_headers
    ).json()
    assert second["items"][0]["id"] < first["items"][0]["id"]
    assert (
        client.get("/api/v1/admin/auditoria?cursor=abc", headers=admin_headers).status_code == 422
    )


def test_forged_forwarding_headers_do_not_reach_the_ledger(  # type: ignore[no-untyped-def]
    client, coord_a_headers, two_sites
) -> None:
    """Client-sent X-Forwarded-For / X-Correlation-Id are not written to the audit ledger (A5)."""
    from sqlalchemy import select

    from app.core.db import system_session
    from app.models import Auditoria

    r = client.put(
        f"/api/v1/sitios/{two_sites['a']}/contacto",
        json={"nombre": "Forense", "telefono": "55 1234 5678", "correo": None},
        headers={
            **coord_a_headers,
            "X-Forwarded-For": "203.0.113.9",
            "X-Correlation-Id": "forged-by-client-12345",
        },
    )
    assert r.status_code == 200, r.text
    server_cid = r.headers["X-Correlation-Id"]
    assert server_cid != "forged-by-client-12345"
    with system_session() as s:
        row = (
            s.execute(
                select(Auditoria)
                .where(Auditoria.entidad == "sitio", Auditoria.entidad_id == str(two_sites["a"]))
                .order_by(Auditoria.id.desc())
            )
            .scalars()
            .first()
        )
    assert row is not None
    assert row.ip != "203.0.113.9"
    assert row.correlation_id == server_cid
