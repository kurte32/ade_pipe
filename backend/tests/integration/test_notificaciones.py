"""HU-14: outbox delivery and coordinator notification feed."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.db import system_session
from app.jobs import outbox
from app.modules.notificaciones.graph import LogNotifier, get_notifier

pytestmark = pytest.mark.integration

CONTACTO = {"nombre": "Pedro", "telefono": "5500000000"}


def _devolver(client, coord_headers, admin_headers, sid):  # type: ignore[no-untyped-def]
    r = client.put(f"/api/v1/sitios/{sid}/contacto", json=CONTACTO, headers=coord_headers)
    r = client.post(
        f"/api/v1/sitios/{sid}/transiciones",
        json={"estatus_destino": "dueno_localizado"},
        headers={**coord_headers, "If-Match": f'"{r.json()["etag"]}"'},
    )
    assert r.status_code == 201
    r = client.post(
        f"/api/v1/admin/sitios/{sid}/devolver",
        json={
            "estatus_destino": "sitio_prospectado",
            "motivo": "calidad_datos",
            "comentario": "Faltan datos del dueño",
        },
        headers={**admin_headers, "If-Match": f'"{r.json()["etag"]}"'},
    )
    assert r.status_code == 200, r.text


def test_notifier_selection_local_is_log() -> None:
    assert isinstance(get_notifier(), LogNotifier)


def test_outbox_job_delivers_and_feed_marks_read(  # type: ignore[no-untyped-def]
    client, coord_a_headers, coord_b_headers, admin_headers, two_sites
):
    sid = two_sites["a"]
    _devolver(client, coord_a_headers, admin_headers, sid)
    outbox.run()
    feed = client.get("/api/v1/notificaciones", headers=coord_a_headers).json()
    mine = [n for n in feed["items"] if n["sitio_id"] == sid]
    assert len(mine) == 1
    note = mine[0]
    assert note["estado"] == "enviada"
    assert note["enviada_utc"]
    assert note["leida"] is False
    assert feed["no_leidas"] >= 1
    # coordinator B cannot see or read A's notification (RLS on destinatario_oid)
    other = client.get("/api/v1/notificaciones", headers=coord_b_headers).json()
    assert all(n["id"] != note["id"] for n in other["items"])
    assert (
        client.post(
            f"/api/v1/notificaciones/{note['id']}/leer", headers=coord_b_headers
        ).status_code
        == 404
    )
    r = client.post(f"/api/v1/notificaciones/{note['id']}/leer", headers=coord_a_headers)
    assert r.status_code == 200
    assert r.json()["leida"] is True
    # admin role has no notification feed
    assert client.get("/api/v1/notificaciones", headers=admin_headers).status_code == 403


def test_outbox_retries_with_backoff(
    client, coord_a_headers, admin_headers, two_sites, monkeypatch
):  # type: ignore[no-untyped-def]
    sid = two_sites["a"]
    _devolver(client, coord_a_headers, admin_headers, sid)

    class Failing:
        def send(self, oid: str, body: dict) -> None:  # type: ignore[type-arg]
            raise RuntimeError("Graph 503 secret-token-should-not-matter")

    monkeypatch.setattr(outbox, "get_notifier", lambda: Failing())
    outbox.run()
    with system_session() as s:
        row = s.execute(
            text(
                "SELECT intentos, estado, ultimo_error, siguiente_intento_utc, creado_utc "
                "FROM notificacion_outbox WHERE sitio_id = :s"
            ),
            {"s": sid},
        ).one()
    assert row.intentos == 1
    assert row.estado == "pendiente"
    assert row.ultimo_error == "RuntimeError"  # unknown message text is not persisted (C9)
    assert "secret" not in row.ultimo_error
    assert row.siguiente_intento_utc > row.creado_utc
    # not due yet, so a second run does not touch it
    outbox.run()
    with system_session() as s:
        intentos = s.execute(
            text("SELECT intentos FROM notificacion_outbox WHERE sitio_id = :s"), {"s": sid}
        ).scalar()
    assert intentos == 1


def test_reasignar_moves_pending_notifications(  # type: ignore[no-untyped-def]
    client, coord_a_headers, admin_headers, two_sites
):
    """DAT-5: an unsent return notice follows the site; the old coordinator must not get it."""
    from sqlalchemy import text

    from app.core.db import system_session

    sid = two_sites["a"]
    _devolver(client, coord_a_headers, admin_headers, sid)
    etag = client.get(f"/api/v1/sitios/{sid}", headers=admin_headers).headers["etag"].strip('"')
    r = client.post(
        f"/api/v1/admin/sitios/{sid}/reasignar",
        json={"coordinador_oid": str(two_sites["oid_b"])},
        headers={**admin_headers, "If-Match": f'"{etag}"'},
    )
    assert r.status_code == 200, r.text
    with system_session() as s:
        rows = s.execute(
            text("SELECT destinatario_oid, estado FROM notificacion_outbox WHERE sitio_id = :id"),
            {"id": sid},
        ).all()
    assert rows, "the return must have queued a notification"
    for destinatario, estado in rows:
        if estado == "pendiente":
            assert str(destinatario).lower() == str(two_sites["oid_b"]).lower()
