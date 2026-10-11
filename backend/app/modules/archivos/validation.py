"""File validation rules (TDD 5.3, 9.1, RNF-05): real type by signature, PDF structure, limits."""

from __future__ import annotations

import math
import re
import unicodedata
import uuid
from typing import IO
from urllib.parse import quote

import filetype
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.config import Settings
from app.core.errors import AppError, unprocessable

PDF_MIME = "application/pdf"
PHOTO_MIMES: dict[str, str] = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
EXTENSIONS: dict[str, str] = {PDF_MIME: "pdf", **PHOTO_MIMES}
TIPOS = ("foto", "documento")


def extension_for(content_type: str) -> str:
    try:
        return EXTENSIONS[content_type]
    except KeyError as exc:
        raise unprocessable(f"Tipo de contenido no admitido: {content_type}") from exc


def safe_filename(name: str) -> str:
    base = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "archivo"
    return base[:120]


def validate_session_request(
    settings: Settings, tipo: str, content_type: str, bytes_total: int, tipo_documento: str | None
) -> None:
    if tipo not in TIPOS:
        raise unprocessable("tipo debe ser 'foto' o 'documento'")
    if bytes_total <= 0:
        raise unprocessable("bytes_total debe ser mayor que cero")
    if tipo == "documento":
        if content_type != PDF_MIME:
            raise unprocessable("Los documentos deben ser PDF")
        if not tipo_documento:
            raise unprocessable("tipo_documento es obligatorio para documentos")
        if bytes_total > settings.pdf_max_bytes:
            raise unprocessable(
                f"El PDF excede el tamaño máximo de {settings.pdf_max_bytes // (1024 * 1024)} MB"
            )
    else:
        if content_type not in PHOTO_MIMES:
            raise unprocessable("Las fotos deben ser JPEG, PNG o WebP")
        if bytes_total > settings.photo_max_bytes:
            raise unprocessable(
                f"La foto excede el tamaño máximo de {settings.photo_max_bytes // 1024} KB"
            )


def parts_for(bytes_total: int, chunk: int) -> int:
    return max(1, math.ceil(bytes_total / chunk))


def expected_part_size(n: int, bytes_total: int, chunk: int, partes_total: int) -> int:
    if n < partes_total - 1:
        return chunk
    return bytes_total - chunk * (partes_total - 1)


def detect_type(head: bytes) -> str | None:
    """Real MIME type from the first bytes, independent of the declared Content-Type."""
    if head.startswith(b"%PDF"):
        return PDF_MIME
    kind = filetype.guess(head)
    return str(kind.mime) if kind is not None else None


def validate_pdf(stream: IO[bytes], max_pages: int) -> int:
    """Return the page count. Rejects encrypted, corrupt, or oversized PDFs."""
    try:
        reader = PdfReader(stream)
        if reader.is_encrypted:
            raise unprocessable("El PDF está cifrado; sube una copia sin contraseña")
        pages = len(reader.pages)
    except AppError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as exc:
        raise unprocessable("El PDF está dañado o no se puede leer") from exc
    if pages > max_pages:
        raise unprocessable(f"El PDF tiene {pages} páginas; el máximo es {max_pages}")
    if pages == 0:
        raise unprocessable("El PDF no tiene páginas")
    return pages


def document_path(sitio_id: int, tipo: str, archivo_id: uuid.UUID, sha256: str, ext: str) -> str:
    return f"pipeline/{sitio_id}/{tipo}/{archivo_id}_{sha256}.{ext}"


def staging_path(session_id: uuid.UUID, nombre_original: str) -> str:
    return f"subidas/{session_id}/{safe_filename(nombre_original)}"


_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Parse a single-range header into (start, end) inclusive. None when absent."""
    if not header:
        return None
    m = _RANGE_RE.match(header.strip())
    if not m or size <= 0:
        raise _unsatisfiable(size)
    start_s, end_s = m.groups()
    if start_s == "" and end_s == "":
        raise _unsatisfiable(size)
    if start_s == "":
        suffix = int(end_s)
        if suffix == 0:
            raise _unsatisfiable(size)
        start = max(0, size - suffix)
        end = size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s else size - 1
        end = min(end, size - 1)
    if start >= size or start > end:
        raise _unsatisfiable(size)
    return start, end


def _unsatisfiable(size: int) -> AppError:
    return AppError(
        416,
        "range-not-satisfiable",
        "Rango no satisfacible",
        "El rango solicitado no es válido para este archivo.",
        headers={"Content-Range": f"bytes */{size}"},
    )


def content_disposition(nombre: str, inline: bool) -> str:
    kind = "inline" if inline else "attachment"
    ascii_name = safe_filename(nombre)
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(nombre, safe='')}"
