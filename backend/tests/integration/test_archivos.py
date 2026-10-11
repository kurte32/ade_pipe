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


# --- promote job (audit B-06, C8) -----------------------------------------------------------


def _park_in_scan(client, headers, sitio_id, data, monkeypatch):  # type: ignore[no-untyped-def]
    """Upload fully and leave the session in 'escaneando' (Defender mode, no tag yet)."""
    from app.modules.archivos import router as archivos_router
    from app.modules.archivos.scan import DefenderScanner

    monkeypatch.setattr(archivos_router, "get_scanner", lambda s, st: DefenderScanner(st))
    r = _start(client, headers, sitio_id, data)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    _send_parts(client, headers, sid, data, r.json()["tamano_parte"])
    done = client.post(f"/api/v1/subidas/{sid}/completar", headers=headers)
    assert done.status_code == 202, done.text
    return uuid.UUID(sid)


def _tag(sid, value):  # type: ignore[no-untyped-def]
    from app.modules.archivos.scan import DEFENDER_TAG

    with system_session() as s:
        path = s.get(SubidaSesion, sid).blob_staging
    get_blob_store().set_tags("staging", path, {DEFENDER_TAG: value})
    return path


def _estado(sid):  # type: ignore[no-untyped-def]
    with system_session() as s:
        sub = s.get(SubidaSesion, sid)
        return sub.estado, sub.archivo_id


def test_promote_job_isolates_failures_and_scan_outcomes(  # type: ignore[no-untyped-def]
    client, coord_a_headers, two_sites, monkeypatch
) -> None:
    from app.jobs import promote as promote_job
    from app.modules.archivos import service as archivos_service
    from app.modules.archivos.scan import DefenderScanner

    store = get_blob_store()
    monkeypatch.setattr(promote_job, "get_scanner", lambda s, st: DefenderScanner(st))
    ok = _park_in_scan(client, coord_a_headers, two_sites["a"], make_pdf(1), monkeypatch)
    boom = _park_in_scan(client, coord_a_headers, two_sites["a"], make_pdf(2), monkeypatch)
    bad = _park_in_scan(client, coord_a_headers, two_sites["a"], make_pdf(3), monkeypatch)
    waiting = _park_in_scan(client, coord_a_headers, two_sites["a"], make_pdf(4), monkeypatch)
    _tag(ok, "No threats found")
    boom_path = _tag(boom, "No threats found")
    bad_path = _tag(bad, "Malicious")

    real_promote = archivos_service.promote

    def flaky(session, claims, st, settings, subida):  # type: ignore[no-untyped-def]
        if subida.id == boom:
            raise RuntimeError("injected failure mid-batch")
        return real_promote(session, claims, st, settings, subida)

    monkeypatch.setattr(archivos_service, "promote", flaky)
    counts = promote_job.run()
    assert counts.get("failed") == 1 and counts.get("malicious") == 1

    assert _estado(ok)[0] == "publicada"  # not rolled back by the later failure
    assert _estado(boom)[0] == "escaneando"
    assert store.exists("staging", boom_path)  # source kept, so the retry can still succeed
    assert _estado(bad)[0] == "rechazada"
    assert not store.exists("staging", bad_path)
    assert _estado(waiting)[0] == "escaneando"  # no tag yet -> pending

    monkeypatch.setattr(archivos_service, "promote", real_promote)
    promote_job.run()
    assert _estado(boom)[0] == "publicada"


def test_promote_rerun_after_lost_commit_registers_existing_copy(  # type: ignore[no-untyped-def]
    client, coord_a_headers, two_sites, monkeypatch
) -> None:
    """Blob copied and staging deleted, but the DB commit was lost: the rerun must finish (B-06)."""
    from app.jobs import promote as promote_job
    from app.modules.archivos import service as archivos_service
    from app.modules.archivos.scan import DefenderScanner

    store = get_blob_store()
    monkeypatch.setattr(promote_job, "get_scanner", lambda s, st: DefenderScanner(st))
    sid = _park_in_scan(client, coord_a_headers, two_sites["a"], make_pdf(5), monkeypatch)
    _tag(sid, "No threats found")
    with system_session() as s:
        sub = s.get(SubidaSesion, sid)
        archivo_id, dst = archivos_service.document_destination(sub)
        staging = sub.blob_staging
    # what a previous attempt did before its transaction was lost:
    store.copy_staging_to_documents(staging, dst)
    store.delete("staging", staging)

    promote_job.run()
    estado, registered = _estado(sid)
    assert estado == "publicada"
    assert registered == archivo_id
    assert store.exists("documents", dst)


def test_purge_job_isolates_a_failing_file(  # type: ignore[no-untyped-def]
    client, coord_a_headers, two_sites, monkeypatch
) -> None:
    """One file failing to purge must not roll back the others (audit B-06)."""
    from app.jobs import purge as purge_job

    _, d1 = _upload(client, coord_a_headers, two_sites["a"], make_pdf(1))
    _, d2 = _upload(
        client, coord_a_headers, two_sites["a"], make_pdf(2), tipo_documento="escritura_hipoteca"
    )
    a1, a2 = d1.json()["id"], d2.json()["id"]
    with system_session() as s:
        s.execute(
            text("UPDATE sitio_archivo SET purga_utc = :t WHERE id IN (:a, :b)"),
            {"t": to_utc_naive(utcnow()) - timedelta(days=1), "a": a1, "b": a2},
        )
        failing_path = s.get(SitioArchivo, uuid.UUID(a1)).ruta_blob

    real = get_blob_store()

    class FailingStore:
        def delete(self, which, path):  # type: ignore[no-untyped-def]
            if path == failing_path:
                raise RuntimeError("injected storage failure")
            real.delete(which, path)

    monkeypatch.setattr(purge_job, "get_blob_store", lambda: FailingStore())
    counts = purge_job.run()
    assert counts.get("failed", 0) >= 1
    with system_session() as s:
        assert s.get(SitioArchivo, uuid.UUID(a1)).estado == "publicado"
        assert s.get(SitioArchivo, uuid.UUID(a2)).estado == "purgado"
    assert real.exists("documents", failing_path)
