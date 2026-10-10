"""HU-07, HU-08, HU-13, offline replay semantics (ADR-005) and admin returns."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.core.db import system_session

pytestmark = pytest.mark.integration

CONTACTO = {"nombre": "María López", "telefono": "55 1234 5678", "correo": "maria@example.com"}
VISITA = {"frente_m": "8.50", "fondo_m": "12.00", "notas": "esquina"}


def _etag(client, headers, sitio_id):  # type: ignore[no-untyped-def]
    r = client.get(f"/api/v1/sitios/{sitio_id}", headers=headers)
    assert r.status_code == 200
    return r.headers["ETag"].strip('"')


def test_contacto_upsert_and_idempotent_replay(client, coord_a_headers, two_sites):  # type: ignore[no-untyped-def]
    key = f"k-{uuid.uuid4().hex}"
    h = {**coord_a_headers, "Idempotency-Key": key}
    r1 = client.put(f"/api/v1/sitios/{two_sites['a']}/contacto", json=CONTACTO, headers=h)
    assert r1.status_code == 200, r1.text
    assert r1.json()["telefono"] == "5512345678"
    assert r1.headers["ETag"]
    r2 = client.put(f"/api/v1/sitios/{two_sites['a']}/contacto", json=CONTACTO, headers=h)
    assert r2.status_code == 200
    assert r2.json() == r1.json()
    # same key, different payload -> 422
    r3 = client.put(
        f"/api/v1/sitios/{two_sites['a']}/contacto", json={**CONTACTO, "nombre": "Otra"}, headers=h
    )
    assert r3.status_code == 422
    # editing without key updates and bumps the etag
    r4 = client.put(
        f"/api/v1/sitios/{two_sites['a']}/contacto",
        json={**CONTACTO, "nombre": "Otra"},
        headers=coord_a_headers,
    )
    assert r4.status_code == 200
    assert r4.json()["nombre"] == "Otra"
    assert r4.json()["etag"] != r1.json()["etag"]


def test_contacto_validation(client, coord_a_headers, two_sites):  # type: ignore[no-untyped-def]
    r = client.put(
        f"/api/v1/sitios/{two_sites['a']}/contacto",
        json={"nombre": "x", "telefono": "123"},
        headers=coord_a_headers,
    )
    assert r.status_code == 422
    assert r.json()["type"].endswith("/validation")


def test_contacto_on_foreign_site_is_404(client, coord_a_headers, two_sites):  # type: ignore[no-untyped-def]
    r = client.put(
        f"/api/v1/sitios/{two_sites['b']}/contacto", json=CONTACTO, headers=coord_a_headers
    )
    assert r.status_code == 404
    with system_session() as s:
        n = s.execute(
            text("SELECT COUNT(*) FROM sitio_contacto WHERE sitio_id = :b"), {"b": two_sites["b"]}
        ).scalar()
    assert n == 0


def test_transition_requires_if_match(client, coord_a_headers, two_sites):  # type: ignore[no-untyped-def]
    r = client.post(
        f"/api/v1/sitios/{two_sites['a']}/transiciones",
        json={"estatus_destino": "dueno_localizado"},
        headers=coord_a_headers,
    )
    assert r.status_code == 428


def test_transition_stale_if_match(client, coord_a_headers, two_sites):  # type: ignore[no-untyped-def]
    r = client.post(
        f"/api/v1/sitios/{two_sites['a']}/transiciones",
        json={"estatus_destino": "dueno_localizado"},
        headers={**coord_a_headers, "If-Match": '"0000000000000000"'},
    )
    assert r.status_code == 412
    assert r.json()["current"]["id"] == two_sites["a"]


def test_transition_without_requirements(client, coord_a_headers, two_sites):  # type: ignore[no-untyped-def]
    etag = _etag(client, coord_a_headers, two_sites["a"])
    r = client.post(
        f"/api/v1/sitios/{two_sites['a']}/transiciones",
        json={"estatus_destino": "dueno_localizado"},
        headers={**coord_a_headers, "If-Match": f'"{etag}"'},
    )
    assert r.status_code == 422
    assert r.json()["faltantes"]


def test_skip_step_rejected(client, coord_a_headers, two_sites):  # type: ignore[no-untyped-def]
    etag = _etag(client, coord_a_headers, two_sites["a"])
    r = client.post(
        f"/api/v1/sitios/{two_sites['a']}/transiciones",
        json={"estatus_destino": "primera_visita"},
        headers={**coord_a_headers, "If-Match": f'"{etag}"'},
    )
    assert r.status_code == 422
    assert r.json()["estatus_siguiente"] == "dueno_localizado"


def test_full_chain_with_threaded_etag(client, coord_a_headers, two_sites):  # type: ignore[no-untyped-def]
    sid = two_sites["a"]
    r = client.put(f"/api/v1/sitios/{sid}/contacto", json=CONTACTO, headers=coord_a_headers)
    etag = r.json()["etag"]
    key = f"t-{uuid.uuid4().hex}"
    r = client.post(
        f"/api/v1/sitios/{sid}/transiciones",
        json={"estatus_destino": "dueno_localizado"},
        headers={**coord_a_headers, "If-Match": f'"{etag}"', "Idempotency-Key": key},
    )
    assert r.status_code == 201, r.text
    assert r.json()["estatus"] == "dueno_localizado"
    etag2 = r.json()["etag"]
    assert etag2 != etag
    # replay of the same transition returns the stored response, not a 412 or 422
    r_replay = client.post(
        f"/api/v1/sitios/{sid}/transiciones",
        json={"estatus_destino": "dueno_localizado"},
        headers={**coord_a_headers, "If-Match": f'"{etag}"', "Idempotency-Key": key},
    )
    assert r_replay.status_code == 201
    assert r_replay.json()["etag"] == etag2
    r = client.put(f"/api/v1/sitios/{sid}/visita", json=VISITA, headers=coord_a_headers)
    assert r.status_code == 200, r.text
    etag3 = r.json()["etag"]
    r = client.post(
        f"/api/v1/sitios/{sid}/transiciones",
        json={"estatus_destino": "primera_visita"},
        headers={**coord_a_headers, "If-Match": f'"{etag3}"'},
    )
    assert r.status_code == 201, r.text
    assert r.json()["estatus"] == "primera_visita"
    # documents are required for the last step
    r = client.post(
        f"/api/v1/sitios/{sid}/transiciones",
        json={"estatus_destino": "recepcion_documentos"},
        headers={**coord_a_headers, "If-Match": f'"{r.json()["etag"]}"'},
    )
    assert r.status_code == 422
    assert any("documento" in f for f in r.json()["faltantes"])
    hist = client.get(f"/api/v1/sitios/{sid}/historial", headers=coord_a_headers).json()
    assert [h["estatus_nuevo"] for h in hist] == ["primera_visita", "dueno_localizado"]
    assert all(h["tipo"] == "avance" and h["origen"] == "pwa" for h in hist)


def test_foreign_site_transition_404(client, coord_a_headers, two_sites):  # type: ignore[no-untyped-def]
    r = client.post(
        f"/api/v1/sitios/{two_sites['b']}/transiciones",
        json={"estatus_destino": "dueno_localizado"},
        headers={**coord_a_headers, "If-Match": '"00"'},
    )
    assert r.status_code == 404


def test_propose_discard(client, coord_a_headers, admin_headers, two_sites):  # type: ignore[no-untyped-def]
    sid = two_sites["a"]
    etag = _etag(client, coord_a_headers, sid)
    r = client.post(
        f"/api/v1/sitios/{sid}/transiciones",
        json={"estatus_destino": "descartado"},
        headers={**coord_a_headers, "If-Match": f'"{etag}"'},
    )
    assert r.status_code == 422
    r = client.post(
        f"/api/v1/sitios/{sid}/transiciones",
        json={"estatus_destino": "descartado", "comentario": "El local ya fue rentado"},
        headers={**coord_a_headers, "If-Match": f'"{etag}"'},
    )
    assert r.status_code == 201
    assert r.json()["estatus"] == "sitio_prospectado"
    assert r.json()["en_revision_admin"] is True
    # admin confirms the discard
    etag = r.json()["etag"]
    r = client.post(
        f"/api/v1/admin/sitios/{sid}/descartar",
        json={"motivo": "otro", "comentario": "Confirmado por el administrador"},
        headers={**admin_headers, "If-Match": f'"{etag}"'},
    )
    assert r.status_code == 200, r.text
    assert r.json()["estatus"] == "descartado"
    assert r.json()["en_revision_admin"] is False
    # no further captures on a terminal site
    r = client.put(f"/api/v1/sitios/{sid}/contacto", json=CONTACTO, headers=coord_a_headers)
    assert r.status_code == 422


def test_devolver_validation(client, admin_headers, coord_a_headers, two_sites):  # type: ignore[no-untyped-def]
    sid = two_sites["a"]
    etag = _etag(client, admin_headers, sid)
    bad_motivo = client.post(
        f"/api/v1/admin/sitios/{sid}/devolver",
        json={"estatus_destino": "sitio_prospectado", "motivo": "nope", "comentario": "comentario"},
        headers={**admin_headers, "If-Match": f'"{etag}"'},
    )
    assert bad_motivo.status_code == 422
    not_earlier = client.post(
        f"/api/v1/admin/sitios/{sid}/devolver",
        json={
            "estatus_destino": "sitio_prospectado",
            "motivo": "calidad_datos",
            "comentario": "comentario",
        },
        headers={**admin_headers, "If-Match": f'"{etag}"'},
    )
    assert not_earlier.status_code == 422
    forbidden = client.post(
        f"/api/v1/admin/sitios/{sid}/devolver",
        json={
            "estatus_destino": "sitio_prospectado",
            "motivo": "calidad_datos",
            "comentario": "comentario",
        },
        headers={**coord_a_headers, "If-Match": f'"{etag}"'},
    )
    assert forbidden.status_code == 403


def test_devolver_happy_path(client, admin_headers, coord_a_headers, two_sites):  # type: ignore[no-untyped-def]
    sid = two_sites["a"]
    # advance to dueno_localizado first
    r = client.put(f"/api/v1/sitios/{sid}/contacto", json=CONTACTO, headers=coord_a_headers)
    r = client.post(
        f"/api/v1/sitios/{sid}/transiciones",
        json={"estatus_destino": "dueno_localizado"},
        headers={**coord_a_headers, "If-Match": f'"{r.json()["etag"]}"'},
    )
    assert r.status_code == 201
    etag = _etag(client, admin_headers, sid)
    r = client.post(
        f"/api/v1/admin/sitios/{sid}/devolver",
        json={
            "estatus_destino": "sitio_prospectado",
            "motivo": "contacto_invalido",
            "comentario": "El teléfono no contesta",
        },
        headers={**admin_headers, "If-Match": f'"{etag}"'},
    )
    assert r.status_code == 200, r.text
    assert r.json()["estatus"] == "sitio_prospectado"
    assert r.json()["devuelto"] is True
    # coordinator sees the return with the comment; contact data is kept
    d = client.get(f"/api/v1/sitios/{sid}", headers=coord_a_headers).json()
    assert d["devuelto"] is True
    assert d["devolucion_motivo"] == "contacto_invalido"
    assert d["devolucion_comentario"] == "El teléfono no contesta"
    assert d["contacto"]["nombre"] == CONTACTO["nombre"]
    hist = client.get(f"/api/v1/sitios/{sid}/historial", headers=admin_headers).json()
    assert hist[0]["tipo"] == "devolucion" and hist[0]["origen"] == "admin"
    assert hist[0]["motivo"] == "contacto_invalido"
    # ledger rows exist
    with system_session() as s:
        n = s.execute(
            text("SELECT COUNT(*) FROM sitio_estatus_historial WHERE sitio_id = :s"), {"s": sid}
        ).scalar()
    assert n == 2
    # notification queued and visible only to the coordinator
    notes = client.get("/api/v1/notificaciones", headers=coord_a_headers).json()
    mine = [n for n in notes["items"] if n["sitio_id"] == sid]
    assert mine and mine[0]["estado"] == "pendiente"
    assert mine[0]["cuerpo"]["motivo_nombre"]
    assert "telefono" not in mine[0]["cuerpo"]
    # advancing again clears the return flag
    etag = d["etag"]
    r = client.post(
        f"/api/v1/sitios/{sid}/transiciones",
        json={"estatus_destino": "dueno_localizado"},
        headers={**coord_a_headers, "If-Match": f'"{etag}"'},
    )
    assert r.status_code == 201
    assert r.json()["devuelto"] is False
    assert r.json()["devolucion_comentario"] is None


def test_reasignar(client, admin_headers, coord_a_headers, coord_b_headers, two_sites):  # type: ignore[no-untyped-def]
    sid = two_sites["a"]
    client.put(f"/api/v1/sitios/{sid}/contacto", json=CONTACTO, headers=coord_a_headers)
    etag = _etag(client, admin_headers, sid)
    r = client.post(
        f"/api/v1/admin/sitios/{sid}/reasignar",
        json={"coordinador_oid": str(two_sites["oid_b"])},
        headers={**admin_headers, "If-Match": f'"{etag}"'},
    )
    assert r.status_code == 200, r.text
    assert r.json()["coordinador_oid"] == str(two_sites["oid_b"])
    assert client.get(f"/api/v1/sitios/{sid}", headers=coord_a_headers).status_code == 404
    d = client.get(f"/api/v1/sitios/{sid}", headers=coord_b_headers)
    assert d.status_code == 200
    assert d.json()["contacto"]["nombre"] == CONTACTO["nombre"]  # child rows moved too
    # delta for A reports the site as removed
    delta = client.get(f"/api/v1/sitios/delta?conocidos={sid}", headers=coord_a_headers).json()
    assert sid in delta["removed_ids"]
    # same coordinator again -> 422
    r = client.post(
        f"/api/v1/admin/sitios/{sid}/reasignar",
        json={"coordinador_oid": str(two_sites["oid_b"])},
        headers={**admin_headers, "If-Match": f'"{r.json()["etag"]}"'},
    )
    assert r.status_code == 422


def test_catalogos(client, coord_a_headers):  # type: ignore[no-untyped-def]
    r = client.get("/api/v1/catalogos", headers=coord_a_headers)
    assert r.status_code == 200
    body = r.json()
    assert [e["codigo"] for e in body["estatus"]][:4] == [
        "sitio_prospectado",
        "dueno_localizado",
        "primera_visita",
        "recepcion_documentos",
    ]
    assert any(m["codigo"] == "calidad_datos" for m in body["motivos_devolucion"])
    assert len(body["tipos_documento"]) == 4
