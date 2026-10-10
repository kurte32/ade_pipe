"""HU-03, HU-04 and the reload rules of TDD 8.4 against the live stack.

The test file is the synthetic sample with origen_id shifted by +900000 so it never collides
with seeded data. Everything created here is removed at the end of the module.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from app.core.db import system_session
from app.models import ESTATUS_DUENO
from tests.conftest import DEV_IDP

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SAMPLE = FIXTURES / "pipeline_nacional_mx_20261009_SINTETICO.xlsx"
OFFSET = 900_000


def _shifted_xlsx(user_override: dict[int, str] | None = None) -> bytes:
    wb = load_workbook(SAMPLE)
    ws = wb.worksheets[0]
    for r in ws.iter_rows(min_row=2):
        cell = r[0]
        cell.value = int(cell.value) + OFFSET
        if user_override and cell.value in user_override:
            r[1].value = user_override[cell.value]
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(client, headers, data: bytes, name: str = "carga.xlsx"):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/v1/admin/cargas",
        headers=headers,
        files={"file": (name, data, "application/octet-stream")},
    )


def _rows(client, headers, lote_id: str, resultado: str | None = None) -> list[dict]:  # type: ignore[no-untyped-def]
    q = "?limit=500" + (f"&resultado={resultado}" if resultado else "")
    r = client.get(f"/api/v1/admin/cargas/{lote_id}{q}", headers=headers)
    assert r.status_code == 200, r.text
    return list(r.json()["filas"]["items"])


def _approve_all(client, headers, lote_id: str) -> None:  # type: ignore[no-untyped-def]
    pending = [
        {"num_fila": f["num_fila"], "decision": "aprobar"}
        for f in _rows(client, headers, lote_id, "advertencia")
        if f["decision_admin"] is None
    ]
    if pending:
        r = client.post(f"/api/v1/admin/cargas/{lote_id}/decisiones", headers=headers, json=pending)
        assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def seeded_equivalencias(client, admin_headers) -> dict[str, str]:  # type: ignore[no-untyped-def]
    users = {u["code"]: u for u in httpx.get(f"{DEV_IDP}/users", timeout=5).json()}
    codes = ["ard", "mmi", "jjt", "jal", "ede", "cmc", "rsp", "usa", "bgl", "jdc"]
    body = [{"usuario_codigo": c, "correo": users[c]["email"], "activo": True} for c in codes]
    r = client.put("/api/v1/admin/equivalencias", headers=admin_headers, json=body)
    assert r.status_code == 200, r.text
    return {c: str(users[c]["oid"]) for c in codes}


@pytest.fixture(scope="module", autouse=True)
def _cleanup() -> Iterator[None]:
    yield
    with system_session() as s:
        ids = (
            s.execute(
                text("SELECT id FROM sitio WHERE origen_id >= :lo AND origen_id < :hi"),
                {"lo": OFFSET, "hi": OFFSET + 100_000},
            )
            .scalars()
            .all()
        )
        for t in (
            "sitio_contacto",
            "sitio_visita",
            "sitio_archivo",
            "subida_sesion",
            "notificacion_outbox",
        ):
            if ids:
                id_list = ",".join(str(i) for i in ids)
                s.execute(text(f"DELETE FROM {t} WHERE sitio_id IN ({id_list})"))  # noqa: S608
        s.execute(
            text("DELETE FROM sitio WHERE origen_id >= :lo AND origen_id < :hi"),
            {"lo": OFFSET, "hi": OFFSET + 100_000},
        )
        s.execute(
            text(
                "DELETE FROM carga_fila_staging WHERE lote_id IN "
                "(SELECT id FROM carga_lote WHERE archivo_nombre LIKE 'carga-test%')"
            )
        )
        s.execute(text("DELETE FROM carga_lote WHERE archivo_nombre LIKE 'carga-test%'"))


def test_coordinator_cannot_use_admin_routes(client, coord_a_headers) -> None:  # type: ignore[no-untyped-def]
    assert client.get("/api/v1/admin/cargas", headers=coord_a_headers).status_code == 403
    assert _upload(client, coord_a_headers, b"x", "carga-test.csv").status_code == 403
    assert client.get("/api/v1/admin/equivalencias", headers=coord_a_headers).status_code == 403


def test_invalid_files_are_422_problems(client, admin_headers) -> None:  # type: ignore[no-untyped-def]
    r = _upload(client, admin_headers, b"PK\x03\x04", "carga-test.xlsm")
    assert r.status_code == 422 and r.headers["content-type"].startswith("application/problem+json")
    r = _upload(client, admin_headers, b"#,USUARIO\n1,ard\n", "carga-test.csv")
    assert r.status_code == 422 and "FECHA" in r.json()["missing"]
    r = _upload(
        client,
        admin_headers,
        (FIXTURES / "pipeline_nacional_mx_20261009_SINTETICO.csv").read_bytes(),
        "carga-test.xlsx",
    )
    assert r.status_code == 422


def test_user_without_equivalence_is_error(client, admin_headers, seeded_equivalencias) -> None:  # type: ignore[no-untyped-def]
    csv = (
        "#,USUARIO,REGION,SITIO,COORDENADAS,GPS,POTENCIAL,CAMPOS,FECHA\n"
        f'{OFFSET + 99_990},zzz,Xalapa,Local,"19.53, -96.92",,Alto,24/24,09/18/2026 14:37:02\n'
    ).encode()
    r = _upload(client, admin_headers, csv, "carga-test-zzz.csv")
    assert r.status_code == 201, r.text
    lote = r.json()
    assert lote["filas_error"] == 1 and lote["filas_ok"] == 0
    rows = _rows(client, admin_headers, lote["id"])
    assert any(m["codigo"] == "usuario_sin_equivalencia" for m in rows[0]["motivos"])
    # error rows cannot be approved
    r = client.post(
        f"/api/v1/admin/cargas/{lote['id']}/decisiones",
        headers=admin_headers,
        json=[{"num_fila": 2, "decision": "aprobar"}],
    )
    assert r.status_code == 422
    # confirm with only error rows inserts nothing
    r = client.post(f"/api/v1/admin/cargas/{lote['id']}/confirmar", headers=admin_headers)
    assert r.status_code == 200 and r.json()["insertadas"] == 0


def test_full_load_preview_decisions_confirm_and_rls(
    client, admin_headers, coord_a_headers, seeded_equivalencias
) -> None:  # type: ignore[no-untyped-def]
    r = _upload(client, admin_headers, _shifted_xlsx(), "carga-test-full.xlsx")
    assert r.status_code == 201, r.text
    lote = r.json()
    assert lote["filas_total"] == 87
    assert lote["filas_error"] == 0
    assert lote["estado"] == "vista_previa"
    warnings = _rows(client, admin_headers, lote["id"], "advertencia")
    motivos = [m["codigo"] for f in warnings for m in f["motivos"]]
    assert motivos.count("nombre_sospechoso") == 5
    assert motivos.count("coordenadas_cercanas") >= 2
    assert motivos.count("campos_incompletos") == 68
    assert lote["filas_advertencia"] == len(warnings)
    assert lote["pendientes_decision"] == len(warnings)

    # confirming with pending decisions is rejected
    r = client.post(f"/api/v1/admin/cargas/{lote['id']}/confirmar", headers=admin_headers)
    assert r.status_code == 422 and r.json()["filas_pendientes"]

    # exclude one suspicious row, approve the rest
    excluded = next(
        f for f in warnings if any(m["codigo"] == "nombre_sospechoso" for m in f["motivos"])
    )
    r = client.post(
        f"/api/v1/admin/cargas/{lote['id']}/decisiones",
        headers=admin_headers,
        json=[{"num_fila": excluded["num_fila"], "decision": "excluir"}],
    )
    assert r.status_code == 200
    _approve_all(client, admin_headers, lote["id"])

    r = client.post(f"/api/v1/admin/cargas/{lote['id']}/confirmar", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["insertadas"] == 86 and body["actualizadas"] == 0 and body["revision"] == 0
    assert body["lote"]["estado"] == "confirmado"
    # second confirm → 409
    assert (
        client.post(
            f"/api/v1/admin/cargas/{lote['id']}/confirmar", headers=admin_headers
        ).status_code
        == 409
    )

    # Admin sees all 86; coordinator 'ard' only their own, with the right oid
    all_items: list[dict] = []
    cursor = None
    while True:
        q = "/api/v1/admin/equivalencias"  # noqa: F841 - keep for readability
        r = client.get(
            "/api/v1/sitios", headers=admin_headers, params={"limit": 200, "cursor": cursor}
        )
        page = r.json()
        all_items += page["items"]
        cursor = page["next_cursor"]
        if not cursor:
            break
    mine = [s for s in all_items if s["origen_id"] >= OFFSET]
    assert len(mine) == 86
    assert all(s["estatus"] == "sitio_prospectado" for s in mine)
    ard_items = client.get("/api/v1/sitios", headers=coord_a_headers, params={"limit": 200}).json()[
        "items"
    ]
    ard_mine = [s for s in ard_items if s["origen_id"] >= OFFSET]
    assert ard_mine and all(s["usuario_codigo"] == "ard" for s in ard_mine)
    assert len(ard_mine) == sum(1 for s in mine if s["usuario_codigo"] == "ard")
    detail = client.get(f"/api/v1/sitios/{ard_mine[0]['id']}", headers=admin_headers).json()
    assert detail["coordinador_oid"] == seeded_equivalencias["ard"]

    # history rows were written for every inserted site
    with system_session() as s:
        n = s.execute(
            text(
                "SELECT COUNT(*) FROM sitio_estatus_historial h JOIN sitio si ON si.id = h.sitio_id "
                "WHERE si.origen_id >= :lo AND h.tipo = 'carga'"
            ),
            {"lo": OFFSET},
        ).scalar()
    assert n == 86


def test_reload_updates_without_touching_progress(
    client, admin_headers, seeded_equivalencias
) -> None:  # type: ignore[no-untyped-def]
    # pick an 'ard' site created by the previous test and advance it manually
    ard_sites = [
        s
        for s in client.get("/api/v1/sitios", headers=admin_headers, params={"limit": 200}).json()[
            "items"
        ]
        if s["origen_id"] >= OFFSET and s["usuario_codigo"] == "ard"
    ]
    target = ard_sites[0]
    with system_session() as s:
        s.execute(
            text("UPDATE sitio SET estatus = :e WHERE id = :id"),
            {"e": ESTATUS_DUENO, "id": target["id"]},
        )

    # reload with USUARIO changed on the advanced site, and on one prospectado site
    other = next(s for s in ard_sites[1:] if s["origen_id"] != target["origen_id"])
    data = _shifted_xlsx({target["origen_id"]: "usa", other["origen_id"]: "usa"})
    r = _upload(client, admin_headers, data, "carga-test-reload.xlsx")
    assert r.status_code == 201, r.text
    lote = r.json()
    rows = {f["origen_id"]: f for f in _rows(client, admin_headers, lote["id"])}
    adv = rows[target["origen_id"]]
    assert adv["accion_prevista"] == "revision"
    assert any(m["codigo"] == "usuario_cambiado_sitio_avanzado" for m in adv["motivos"])
    pro = rows[other["origen_id"]]
    assert pro["accion_prevista"] == "actualizar"
    assert any(m["codigo"] == "usuario_cambiado" for m in pro["motivos"])
    # the row excluded last time is a new insert now
    assert sum(1 for f in rows.values() if f["accion_prevista"] == "insertar") == 1

    _approve_all(client, admin_headers, lote["id"])
    r = client.post(f"/api/v1/admin/cargas/{lote['id']}/confirmar", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["insertadas"] == 1
    assert body["revision"] == 1
    assert body["actualizadas"] == 85

    adv_detail = client.get(f"/api/v1/sitios/{target['id']}", headers=admin_headers).json()
    assert adv_detail["estatus"] == ESTATUS_DUENO  # progress untouched
    assert adv_detail["usuario_codigo"] == "ard"  # not reassigned
    assert adv_detail["en_revision_admin"] is True
    assert adv_detail["coordinador_oid"] == seeded_equivalencias["ard"]
    pro_detail = client.get(f"/api/v1/sitios/{other['id']}", headers=admin_headers).json()
    assert pro_detail["usuario_codigo"] == "usa"  # prospectado site reassigned
    assert pro_detail["coordinador_oid"] == seeded_equivalencias["usa"]


def test_cancel_and_list(client, admin_headers) -> None:  # type: ignore[no-untyped-def]
    csv = (
        "#,USUARIO,REGION,SITIO,COORDENADAS,GPS,POTENCIAL,CAMPOS,FECHA\n"
        f'{OFFSET + 99_991},ard,Xalapa,Local cancelado,"19.60, -96.95",,Alto,24/24,2026-09-18T10:00:00\n'
    ).encode()
    lote = _upload(client, admin_headers, csv, "carga-test-cancel.csv").json()
    r = client.post(f"/api/v1/admin/cargas/{lote['id']}/cancelar", headers=admin_headers)
    assert r.status_code == 200 and r.json()["estado"] == "cancelado"
    assert (
        client.post(
            f"/api/v1/admin/cargas/{lote['id']}/confirmar", headers=admin_headers
        ).status_code
        == 409
    )
    listed = client.get("/api/v1/admin/cargas", headers=admin_headers).json()
    assert any(x["id"] == lote["id"] for x in listed)
    assert (
        client.get(f"/api/v1/admin/cargas/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    )
