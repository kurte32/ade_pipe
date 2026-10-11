from __future__ import annotations

import io
import uuid

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.archivos import validation as v
from tests.fixtures import TINY_JPEG, make_pdf


@pytest.fixture
def settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        auth_tenant_id="t",
        auth_audience="a",
        auth_issuer="i",
        auth_jwks_url="j",
        pdf_max_bytes=1000,
        photo_max_bytes=500,
        pdf_max_pages=50,
    )


def test_session_request_rules(settings: Settings) -> None:
    v.validate_session_request(settings, "documento", "application/pdf", 1000, "uso_de_suelo")
    v.validate_session_request(settings, "foto", "image/jpeg", 500, None)
    for args in [
        ("documento", "image/jpeg", 10, "x"),
        ("documento", "application/pdf", 1001, "x"),
        ("documento", "application/pdf", 10, None),
        ("foto", "application/pdf", 10, None),
        ("foto", "image/gif", 10, None),
        ("foto", "image/png", 501, None),
        ("otro", "image/png", 1, None),
        ("foto", "image/png", 0, None),
    ]:
        with pytest.raises(AppError) as e:
            v.validate_session_request(settings, *args)
        assert e.value.status == 422


def test_parts_math() -> None:
    assert v.parts_for(10, 4) == 3
    assert v.parts_for(8, 4) == 2
    assert v.parts_for(1, 4) == 1
    assert v.expected_part_size(0, 10, 4, 3) == 4
    assert v.expected_part_size(2, 10, 4, 3) == 2
    assert v.expected_part_size(1, 8, 4, 2) == 4


def test_detect_type() -> None:
    assert v.detect_type(make_pdf()[:64]) == "application/pdf"
    assert v.detect_type(TINY_JPEG[:64]) == "image/jpeg"
    assert v.detect_type(b"\x89PNG\r\n\x1a\n" + b"\0" * 56) == "image/png"
    assert v.detect_type(b"not a file at all" + b"\0" * 40) is None
    assert v.detect_type(b"GIF89a" + b"\0" * 58) == "image/gif"


def test_validate_pdf_ok_and_limits() -> None:
    assert v.validate_pdf(io.BytesIO(make_pdf(3)), 50) == 3
    with pytest.raises(AppError, match="páginas"):
        v.validate_pdf(io.BytesIO(make_pdf(51)), 50)
    with pytest.raises(AppError, match="cifrado"):
        v.validate_pdf(io.BytesIO(make_pdf(1, encrypt="secreto")), 50)
    with pytest.raises(AppError, match="dañado"):
        v.validate_pdf(io.BytesIO(b"%PDF-1.4 garbage without xref"), 50)


def test_paths_and_names() -> None:
    aid = uuid.UUID("12345678-1234-4123-8123-123456789abc")
    assert v.document_path(7, "documento", aid, "ab" * 32, "pdf") == (
        f"pipeline/7/documento/{aid}_{'ab' * 32}.pdf"
    )
    assert v.staging_path(aid, "Hipoteca Ñuñoa (final).pdf").startswith(
        f"subidas/{aid}/Hipoteca_Nunoa"
    )
    assert v.safe_filename("../../etc/passwd") == "etc_passwd"
    assert v.safe_filename("") == "archivo"
    assert v.extension_for("image/webp") == "webp"
    with pytest.raises(AppError):
        v.extension_for("text/plain")


def test_content_disposition_rfc5987() -> None:
    cd = v.content_disposition("hipoteca ñ.pdf", inline=False)
    assert cd.startswith('attachment; filename="hipoteca_n.pdf"')
    assert "filename*=UTF-8''hipoteca%20%C3%B1.pdf" in cd
    assert v.content_disposition("f.jpg", inline=True).startswith("inline;")


@pytest.mark.parametrize(
    "header,size,expected",
    [
        (None, 100, None),
        ("bytes=0-9", 100, (0, 9)),
        ("bytes=90-", 100, (90, 99)),
        ("bytes=-10", 100, (90, 99)),
        ("bytes=0-500", 100, (0, 99)),
    ],
)
def test_parse_range(header: str | None, size: int, expected: tuple[int, int] | None) -> None:
    assert v.parse_range(header, size) == expected


@pytest.mark.parametrize(
    "header", ["bytes=100-", "bytes=50-10", "bytes=-0", "bytes=-", "items=0-1"]
)
def test_parse_range_unsatisfiable(header: str) -> None:
    with pytest.raises(AppError) as e:
        v.parse_range(header, 100)
    assert e.value.status == 416
    assert e.value.headers["Content-Range"] == "bytes */100"
