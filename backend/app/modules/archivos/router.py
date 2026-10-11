from __future__ import annotations

import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core import idempotency
from app.core.config import Settings, get_settings
from app.core.errors import unprocessable
from app.core.security import ROLE_ADMIN, ROLE_COORDINADOR, Claims, require_role
from app.core.storage import BlobStore
from app.deps import blob_store, client_ip, get_session, idempotency_key
from app.modules.archivos import service
from app.modules.archivos import validation as v
from app.modules.archivos.scan import get_scanner
from app.modules.archivos.schemas import (
    ArchivoMeta,
    CompletarEscaneando,
    PartesOut,
    SubidaCreate,
    SubidaOut,
)

router = APIRouter(prefix="/api/v1", tags=["archivos"])
_coord = require_role(ROLE_COORDINADOR)
_any_role = require_role(ROLE_COORDINADOR, ROLE_ADMIN)

SUBIDAS_ROUTE = "/api/v1/subidas"


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise unprocessable(f"Identificador de {what} inválido") from exc


# --- subidas -----------------------------------------------------------------------------------


@router.post("/subidas", response_model=SubidaOut, status_code=status.HTTP_201_CREATED)
def crear_subida(
    body: SubidaCreate,
    response: Response,
    claims: Claims = Depends(_coord),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    key: str | None = Depends(idempotency_key),
) -> SubidaOut:
    body_hash = idempotency.request_hash(body.model_dump(mode="json"))

    def work() -> tuple[int, dict[str, object]]:
        subida = service.create_session(session, claims, settings, body)
        return 201, service.subida_out(subida, []).model_dump(mode="json")

    code, out = idempotency.run_once(session, claims, key, SUBIDAS_ROUTE, body_hash, work)
    response.status_code = code
    return SubidaOut.model_validate(out)


@router.get("/subidas/{subida_id}", response_model=SubidaOut)
def ver_subida(
    subida_id: str,
    claims: Claims = Depends(_coord),
    session: Session = Depends(get_session),
    store: BlobStore = Depends(blob_store),
) -> SubidaOut:
    subida = service.get_subida(session, _uuid(subida_id, "sesión"))
    partes = (
        service.received_parts(store, subida) if subida.estado == service.ESTADO_ABIERTA else []
    )
    return service.subida_out(subida, partes)


@router.put("/subidas/{subida_id}/partes/{n}", response_model=PartesOut)
async def subir_parte(
    subida_id: str,
    n: int,
    request: Request,
    claims: Claims = Depends(_coord),
    session: Session = Depends(get_session),
    store: BlobStore = Depends(blob_store),
) -> PartesOut:
    sid = _uuid(subida_id, "sesión")
    subida = await run_in_threadpool(service.get_subida, session, sid)
    expected = await run_in_threadpool(service.expected_part_bytes, subida, n)
    # Never buffer more than the part can legally hold (audit B-05): reject a larger declared
    # Content-Length before reading, and abort the stream as soon as it overruns.
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > expected:
        raise unprocessable(f"La parte {n} debe tener {expected} bytes y declara {declared}")
    buf = bytearray()
    async for chunk in request.stream():
        buf.extend(chunk)
        if len(buf) > expected:
            raise unprocessable(f"La parte {n} debe tener {expected} bytes y excede ese tamaño")
    data = bytes(buf)

    def _work() -> list[int]:
        return service.put_part(session, store, subida, n, data)

    return PartesOut(partes_recibidas=await run_in_threadpool(_work))


@router.post("/subidas/{subida_id}/completar", response_model=ArchivoMeta | CompletarEscaneando)
def completar_subida(
    subida_id: str,
    response: Response,
    claims: Claims = Depends(_coord),
    session: Session = Depends(get_session),
    store: BlobStore = Depends(blob_store),
    settings: Settings = Depends(get_settings),
) -> ArchivoMeta | CompletarEscaneando:
    subida = service.get_subida(session, _uuid(subida_id, "sesión"))
    scanner = get_scanner(settings, store)
    estado, archivo = service.complete(session, claims, store, settings, scanner, subida)
    if estado == "publicado" and archivo is not None:
        return service.archivo_meta(archivo)
    response.status_code = status.HTTP_202_ACCEPTED
    return CompletarEscaneando(id=str(subida.id))


@router.delete("/subidas/{subida_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancelar_subida(
    subida_id: str,
    claims: Claims = Depends(_coord),
    session: Session = Depends(get_session),
    store: BlobStore = Depends(blob_store),
) -> Response:
    subida = service.get_subida(session, _uuid(subida_id, "sesión"))
    service.cancel_session(session, claims, store, subida)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- archivos ----------------------------------------------------------------------------------


@router.get("/archivos/{archivo_id}/meta", response_model=ArchivoMeta)
def archivo_meta(
    archivo_id: str,
    claims: Claims = Depends(_any_role),
    session: Session = Depends(get_session),
) -> ArchivoMeta:
    return service.archivo_meta(service.get_archivo(session, _uuid(archivo_id, "archivo")))


@router.api_route(
    "/archivos/{archivo_id}", methods=["GET", "HEAD"], response_class=StreamingResponse
)
def descargar_archivo(
    archivo_id: str,
    request: Request,
    claims: Claims = Depends(_any_role),
    session: Session = Depends(get_session),
    store: BlobStore = Depends(blob_store),
    ip: str | None = Depends(client_ip),
) -> Response:
    archivo = service.get_archivo(session, _uuid(archivo_id, "archivo"))
    size = archivo.bytes
    rng = v.parse_range(request.headers.get("Range"), size)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": v.content_disposition(
            archivo.nombre_original, inline=archivo.tipo == "foto"
        ),
        "Cache-Control": "private, no-store",
        "ETag": f'"{archivo.sha256}"',
    }
    if rng is None:
        offset, length, code = 0, size, status.HTTP_200_OK
        headers["Content-Length"] = str(size)
    else:
        start, end = rng
        offset, length, code = start, end - start + 1, status.HTTP_206_PARTIAL_CONTENT
        headers["Content-Length"] = str(length)
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    if request.method == "HEAD":
        # Headers only: no bytes leave the server, so no download is recorded.
        return Response(status_code=code, headers=headers, media_type=archivo.content_type)
    service.record_download(session, claims, archivo, ip)
    # Audit row is committed before any byte leaves the server (RNF-07).
    session.commit()
    path, content_type = archivo.ruta_blob, archivo.content_type

    def body() -> Iterator[bytes]:
        yield from store.download("documents", path, offset=offset, length=length)

    return StreamingResponse(body(), status_code=code, media_type=content_type, headers=headers)


@router.delete("/archivos/{archivo_id}", status_code=status.HTTP_204_NO_CONTENT)
def retirar_archivo(
    archivo_id: str,
    claims: Claims = Depends(_coord),
    session: Session = Depends(get_session),
) -> Response:
    service.soft_delete(session, claims, service.get_archivo(session, _uuid(archivo_id, "archivo")))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router", "JSONResponse"]
