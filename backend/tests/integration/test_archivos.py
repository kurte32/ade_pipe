"""HU-09, HU-11, HU-12, HU-16, HU-17: chunked resumable upload, validation, download, purge."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app.core.clock import to_utc_naive, utcnow
from app.core.config import get_settings
from app.core.db import system_session
from app.core.storage import get_blob_store
from app.models import Auditoria, SitioArchivo, SubidaSesion
from tests.fixtures import TINY_JPEG, make_pdf

pytestmark = pytest.mark.integration

CHUNK = get_settings().upload_chunk_bytes


@pytest.fixture(autouse=True)
def _cleanup_blobs(two_sites):  # type: ignore[no-untyped-def]
    yield
    store = get_blob_store()
    with system_session() as s:
        for path in s.execute(
            select(SubidaSesion.blob_staging).where(
                SubidaSesion.sitio_id.in_([two_sites["a"], two_sites["b"]])
            )
        ).scalars():
            store.delete("staging", path)
        for path in s.execute(
            select(SitioArchivo.ruta_blob).where(
                SitioArchivo.sitio_id.in_([two_sites["a"], two_sites["b"]])
            )
        ).scalars():
            store.delete("documents", path)


def _start(
    client,
    headers,
    sitio_id,
    data: bytes,
    *,
    tipo="documento",
    tipo_documento="uso_de_suelo",
    content_type="application/pdf",
    nombre="hipoteca ñ.pdf",
    key=None,
):  # type: ignore[no-untyped-def]
    body = {
        "sitio_id": sitio_id,
        "tipo": tipo,
        "tipo_documento": tipo_documento,
        "nombre_original": nombre,
        "content_type": content_type,
        "bytes_total": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    h = dict(headers)
    if key:
        h["Idempotency-Key"] = key
    return client.post("/api/v1/subidas", json=body, headers=h)


def _send_parts(client, headers, sid: str, data: bytes, chunk: int, skip: set[int] | None = None):  # type: ignore[no-untyped-def]
    n = max(1, -(-len(data) // chunk))
    last = None
    for i in range(n):
        if skip and i in skip:
            continue
        last = client.put(
            f"/api/v1/subidas/{sid}/partes/{i}",
            content=data[i * chunk : (i + 1) * chunk],
            headers={**headers, "Content-Type": "application/octet-stream"},
        )
        assert last.status_code == 200, last.text
    return last


def _upload(client, headers, sitio_id, data: bytes, **kw):  # type: ignore[no-untyped-def]
    r = _start(client, headers, sitio_id, data, **kw)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    _send_parts(client, headers, sid, data, r.json()["tamano_parte"])
    done = client.post(f"/api/v1/subidas/{sid}/completar", headers=headers)
    return sid, done


def test_resumable_three_part_pdf_roundtrip(
    client, coord_a_headers, coord_b_headers, two_sites
) -> None:  # type: ignore[no-untyped-def]
    data = make_pdf(2, pad_bytes=2 * CHUNK + 1000)  # spans three chunks
    r = _start(client, coord_a_headers, two_sites["a"], data, key="k-" + uuid.uuid4().hex[:8])
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["partes_total"] == 3 and s["estado"] == "abierta"
    sid = s["id"]

    # Replaying the same Idempotency-Key returns the same session.
    r2 = _start(
        client, coord_a_headers, two_sites["a"], data, key=r.request.headers["Idempotency-Key"]
    )
    assert r2.status_code == 201 and r2.json()["id"] == sid

    # Send parts 0 and 2, "lose" part 1, then resume.
    _send_parts(client, coord_a_headers, sid, data, CHUNK, skip={1})
    state = client.get(f"/api/v1/subidas/{sid}", headers=coord_a_headers).json()
    assert state["partes_recibidas"] == [0, 2]
    incomplete = client.post(f"/api/v1/subidas/{sid}/completar", headers=coord_a_headers)
    assert incomplete.status_code == 422 and incomplete.json()["partes_faltantes"] == [1]
    assert (
        client.get(f"/api/v1/subidas/{sid}", headers=coord_a_headers).json()["estado"] == "abierta"
    )

    # Foreign coordinator cannot see the session.
    assert client.get(f"/api/v1/subidas/{sid}", headers=coord_b_headers).status_code == 404

    # Re-send part 0 (duplicate) and send part 1, then complete.
    _send_parts(client, coord_a_headers, sid, data, CHUNK, skip={2})
    wrong = client.put(
        f"/api/v1/subidas/{sid}/partes/1",
        content=b"x",
        headers={**coord_a_headers, "Content-Type": "application/octet-stream"},
    )
    assert wrong.status_code == 422
    done = client.post(f"/api/v1/subidas/{sid}/completar", headers=coord_a_headers)
    assert done.status_code == 200, done.text
    meta = done.json()
    assert meta["estado"] == "publicado" and meta["paginas"] == 2 and meta["version"] == 1
    assert meta["sha256"] == hashlib.sha256(data).hexdigest()
    assert (
        client.get(f"/api/v1/subidas/{sid}", headers=coord_a_headers).json()["estado"]
        == "publicada"
    )

    # Completing again is idempotent.
    again = client.post(f"/api/v1/subidas/{sid}/completar", headers=coord_a_headers)
    assert again.status_code == 200 and again.json()["id"] == meta["id"]

    # Download: full, range, foreign, meta, and site detail lists it.
    aid = meta["id"]
    full = client.get(f"/api/v1/archivos/{aid}", headers=coord_a_headers)
    assert full.status_code == 200 and full.content == data
    assert full.headers["content-type"] == "application/pdf"
    assert full.headers["accept-ranges"] == "bytes"
    assert "attachment" in full.headers["content-disposition"]
    assert "filename*=UTF-8''hipoteca%20%C3%B1.pdf" in full.headers["content-disposition"]
    part = client.get(
        f"/api/v1/archivos/{aid}", headers={**coord_a_headers, "Range": "bytes=10-19"}
    )
    assert part.status_code == 206 and part.content == data[10:20]
    assert part.headers["content-range"] == f"bytes 10-19/{len(data)}"
    bad = client.get(
        f"/api/v1/archivos/{aid}", headers={**coord_a_headers, "Range": f"bytes={len(data)}-"}
    )
    assert bad.status_code == 416
    assert client.get(f"/api/v1/archivos/{aid}", headers=coord_b_headers).status_code == 404
    assert (
        client.get(f"/api/v1/archivos/{aid}/meta", headers=coord_a_headers).json()[
            "nombre_original"
        ]
        == "hipoteca ñ.pdf"
    )
    detail = client.get(f"/api/v1/sitios/{two_sites['a']}", headers=coord_a_headers).json()
    assert [a["id"] for a in detail["archivos"]] == [aid]

    # Staging blob is gone, documents blob exists.
    store = get_blob_store()
    with system_session() as s:
        row = s.get(SitioArchivo, uuid.UUID(aid))
        assert row is not None
        assert store.exists("documents", row.ruta_blob)
        assert not store.exists("staging", s.get(SubidaSesion, uuid.UUID(sid)).blob_staging)  # type: ignore[union-attr]
        acciones = {
            a.accion
            for a in s.execute(
                select(Auditoria).where(
                    Auditoria.entidad == "sitio_archivo", Auditoria.entidad_id == aid
                )
            ).scalars()
        }
    assert {"archivo_publicado", "archivo_descargado"} <= acciones


def test_sha256_mismatch_rejects_session(client, coord_a_headers, two_sites) -> None:  # type: ignore[no-untyped-def]
    data = make_pdf(1)
    r = _start(client, coord_a_headers, two_sites["a"], data)
    sid = r.json()["id"]
    tampered = data[:-5] + b"ABCDE"
    _send_parts(client, coord_a_headers, sid, tampered, CHUNK)
    done = client.post(f"/api/v1/subidas/{sid}/completar", headers=coord_a_headers)
    assert done.status_code == 422 and "SHA-256" in done.json()["detail"]
    st = client.get(f"/api/v1/subidas/{sid}", headers=coord_a_headers).json()
    assert st["estado"] == "rechazada" and st["motivo_rechazo"]


def test_encrypted_and_oversized_pdf_rejected(client, coord_a_headers, two_sites) -> None:  # type: ignore[no-untyped-def]
    _, done = _upload(client, coord_a_headers, two_sites["a"], make_pdf(1, encrypt="pw"))
    assert done.status_code == 422 and "cifrado" in done.json()["detail"]
    _, done = _upload(client, coord_a_headers, two_sites["a"], make_pdf(51))
    assert done.status_code == 422 and "páginas" in done.json()["detail"]


def test_declared_type_must_match_content(client, coord_a_headers, two_sites) -> None:  # type: ignore[no-untyped-def]
    fake_pdf = b"GIF89a" + b"\0" * 2000
    _, done = _upload(client, coord_a_headers, two_sites["a"], fake_pdf)
    assert done.status_code == 422 and "no corresponde" in done.json()["detail"]


def test_session_validation_errors(
    client, coord_a_headers, coord_b_headers, admin_headers, two_sites
) -> None:  # type: ignore[no-untyped-def]
    data = make_pdf(1)
    assert _start(client, coord_a_headers, two_sites["b"], data).status_code == 404  # foreign site
    assert (
        _start(
            client, coord_a_headers, two_sites["a"], data, tipo_documento="inexistente"
        ).status_code
        == 422
    )
    assert (
        _start(client, coord_a_headers, two_sites["a"], data, content_type="image/jpeg").status_code
        == 422
    )
    assert _start(client, admin_headers, two_sites["a"], data).status_code == 403
    big = client.post(
        "/api/v1/subidas",
        json={
            "sitio_id": two_sites["a"],
            "tipo": "documento",
            "tipo_documento": "uso_de_suelo",
            "nombre_original": "x.pdf",
            "content_type": "application/pdf",
            "bytes_total": get_settings().pdf_max_bytes + 1,
            "sha256": "a" * 64,
        },
        headers=coord_a_headers,
    )
    assert big.status_code == 422


def test_photo_upload_inline(client, coord_a_headers, two_sites) -> None:  # type: ignore[no-untyped-def]
    sid, done = _upload(
        client,
        coord_a_headers,
        two_sites["a"],
        TINY_JPEG,
        tipo="foto",
        tipo_documento=None,
        content_type="image/jpeg",
        nombre="fachada.jpg",
    )
    assert done.status_code == 200, done.text
    meta = done.json()
    assert meta["tipo"] == "foto" and meta["paginas"] is None and meta["tipo_documento"] is None
    r = client.get(f"/api/v1/archivos/{meta['id']}", headers=coord_a_headers)
    assert r.status_code == 200 and r.content == TINY_JPEG
    assert r.headers["content-disposition"].startswith("inline;")


def test_second_document_bumps_version_and_retires_previous(
    client, coord_a_headers, two_sites
) -> None:  # type: ignore[no-untyped-def]
    _, first = _upload(client, coord_a_headers, two_sites["a"], make_pdf(1))
    _, second = _upload(client, coord_a_headers, two_sites["a"], make_pdf(2))
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["version"] == 2
    old = client.get(f"/api/v1/archivos/{first.json()['id']}/meta", headers=coord_a_headers).json()
    assert old["vigente"] is False
    # A different tipo_documento starts at version 1 and does not retire the other.
    _, other = _upload(
        client, coord_a_headers, two_sites["a"], make_pdf(1), tipo_documento="predial"
    )
    assert other.json()["version"] == 1
    assert (
        client.get(f"/api/v1/archivos/{second.json()['id']}/meta", headers=coord_a_headers).json()[
            "vigente"
        ]
        is True
    )
    # Soft delete (retirar) of the vigente one before recepcion_documentos is allowed.
    assert (
        client.delete(
            f"/api/v1/archivos/{second.json()['id']}", headers=coord_a_headers
        ).status_code
        == 204
    )
    assert (
        client.get(f"/api/v1/archivos/{second.json()['id']}/meta", headers=coord_a_headers).json()[
            "vigente"
        ]
        is False
    )


def test_cancel_session(client, coord_a_headers, two_sites) -> None:  # type: ignore[no-untyped-def]
    data = make_pdf(1)
    sid = _start(client, coord_a_headers, two_sites["a"], data).json()["id"]
    _send_parts(client, coord_a_headers, sid, data, CHUNK)
    assert client.delete(f"/api/v1/subidas/{sid}", headers=coord_a_headers).status_code == 204
    assert (
        client.get(f"/api/v1/subidas/{sid}", headers=coord_a_headers).json()["estado"]
        == "cancelada"
    )
    assert (
        client.post(f"/api/v1/subidas/{sid}/completar", headers=coord_a_headers).status_code == 422
    )


def test_expire_job(client, coord_a_headers, two_sites) -> None:  # type: ignore[no-untyped-def]
    from app.jobs import expire_uploads

    data = make_pdf(1)
    sid = _start(client, coord_a_headers, two_sites["a"], data).json()["id"]
    _send_parts(client, coord_a_headers, sid, data, CHUNK)
    with system_session() as s:
        s.execute(
            text("UPDATE subida_sesion SET expira_utc = :t WHERE id = :id"),
            {"t": to_utc_naive(utcnow()) - timedelta(hours=1), "id": sid},
        )
    expire_uploads.run()
    st = client.get(f"/api/v1/subidas/{sid}", headers=coord_a_headers).json()
    assert st["estado"] == "expirada"
    with system_session() as s:
        path = s.get(SubidaSesion, uuid.UUID(sid)).blob_staging  # type: ignore[union-attr]
    assert get_blob_store().uncommitted_blocks(path) == set()


def test_purge_job_keeps_metadata(client, coord_a_headers, two_sites) -> None:  # type: ignore[no-untyped-def]
    from app.jobs import purge

    _, done = _upload(client, coord_a_headers, two_sites["a"], make_pdf(1))
    aid = done.json()["id"]
    with system_session() as s:
        s.execute(
            text("UPDATE sitio_archivo SET purga_utc = :t WHERE id = :id"),
            {"t": to_utc_naive(utcnow()) - timedelta(days=1), "id": aid},
        )
    purge.run()
    meta = client.get(f"/api/v1/archivos/{aid}/meta", headers=coord_a_headers).json()
    assert meta["estado"] == "purgado"
    assert client.get(f"/api/v1/archivos/{aid}", headers=coord_a_headers).status_code == 410
    with system_session() as s:
        row = s.get(SitioArchivo, uuid.UUID(aid))
        assert row is not None and row.purgado_utc is not None
        assert not get_blob_store().exists("documents", row.ruta_blob)
        audit = s.execute(
            select(Auditoria).where(
                Auditoria.accion == "archivo_purgado", Auditoria.entidad_id == aid
            )
        ).scalar_one()
        assert audit.rol == "Sistema"


def test_oversized_part_rejected_before_reading(client, coord_a_headers, two_sites) -> None:  # type: ignore[no-untyped-def]
    """A part larger than the session allows is refused by Content-Length, unread (audit B-05)."""
    data = make_pdf(1)
    r = _start(client, coord_a_headers, two_sites["a"], data)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    big = b"\0" * (5 * 1024 * 1024)
    resp = client.put(
        f"/api/v1/subidas/{sid}/partes/0",
        content=big,
        headers={**coord_a_headers, "Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 422, resp.text
    assert "declara" in resp.json()["detail"]  # rejected on the declared length, before the body


def test_oversized_streamed_part_aborted(client, coord_a_headers, two_sites) -> None:  # type: ignore[no-untyped-def]
    """Without a Content-Length the stream is cut as soon as it overruns the part (audit B-05)."""
    data = make_pdf(1)
    r = _start(client, coord_a_headers, two_sites["a"], data)
    sid = r.json()["id"]

    def chunks():  # type: ignore[no-untyped-def]
        for _ in range(64):
            yield b"\0" * 65536

    resp = client.put(
        f"/api/v1/subidas/{sid}/partes/0",
        content=chunks(),
        headers={**coord_a_headers, "Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 422, resp.text
    assert "excede" in resp.json()["detail"]
