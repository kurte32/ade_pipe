from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.cargas.parser import cell_to_text, normalize_header, parse_upload

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BASE = "pipeline_nacional_mx_20261009_SINTETICO"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        auth_tenant_id="t",
        auth_audience="a",
        auth_issuer="i",
        auth_jwks_url="j",
        load_max_rows=5000,
    )


@pytest.mark.parametrize("ext", [".csv", ".xlsx", ".xls"])
def test_parse_fixture_formats(settings: Settings, ext: str) -> None:
    data = (FIXTURES / f"{BASE}{ext}").read_bytes()
    parsed = parse_upload(f"carga{ext}", data, settings)
    assert parsed.formato == ext.lstrip(".")
    assert len(parsed.rows) == 87
    assert "REGION" in parsed.columns  # REGIÓN normalized
    first = parsed.rows[0]
    assert first["#"].isdigit()  # type: ignore[union-attr]
    assert first["CAMPOS"] and "/" in first["CAMPOS"]
    assert first["FECHA"] and datetime.strptime(first["FECHA"], "%m/%d/%Y %H:%M:%S")
    assert all(r.get("GPS") is None or isinstance(r["GPS"], str) for r in parsed.rows)


def test_xlsx_cell_types_preserved(settings: Settings) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["#", "FECHA", "GPS", "SITIO"])
    ws.append([560, datetime(2026, 9, 18, 14, 37, 2), 12.0, "Av. Uno"])
    ws.append([561.0, "09/18/2026 14:37:02", 3.5, None])
    buf = io.BytesIO()
    wb.save(buf)
    parsed = parse_upload("x.xlsx", buf.getvalue(), settings)
    assert parsed.rows[0]["#"] == "560"
    assert parsed.rows[0]["FECHA"] == "09/18/2026 14:37:02"
    assert parsed.rows[0]["GPS"] == "12"
    assert parsed.rows[1]["#"] == "561"
    assert parsed.rows[1]["GPS"] == "3.5"
    assert parsed.rows[1]["SITIO"] is None


def test_xlsm_rejected(settings: Settings) -> None:
    with pytest.raises(AppError) as e:
        parse_upload("macros.xlsm", b"PK\x03\x04junk", settings)
    assert e.value.status == 422


def test_unknown_extension_rejected(settings: Settings) -> None:
    with pytest.raises(AppError):
        parse_upload("datos.json", b"{}", settings)


def test_bad_signature_rejected(settings: Settings) -> None:
    csv_bytes = (FIXTURES / f"{BASE}.csv").read_bytes()
    with pytest.raises(AppError, match="firma"):
        parse_upload("fake.xlsx", csv_bytes, settings)
    with pytest.raises(AppError, match="firma"):
        parse_upload("fake.xls", csv_bytes, settings)
    with pytest.raises(AppError, match="no es texto"):
        parse_upload("fake.csv", (FIXTURES / f"{BASE}.xlsx").read_bytes(), settings)


def test_size_and_row_limits() -> None:
    s = Settings(
        auth_tenant_id="t",
        auth_audience="a",
        auth_issuer="i",
        auth_jwks_url="j",
        load_max_rows=10,
        load_max_bytes=100,
    )
    with pytest.raises(AppError, match="MB"):
        parse_upload("x.csv", b"a" * 101, s)
    csv_bytes = (FIXTURES / f"{BASE}.csv").read_bytes()
    s2 = Settings(
        auth_tenant_id="t", auth_audience="a", auth_issuer="i", auth_jwks_url="j", load_max_rows=10
    )
    with pytest.raises(AppError, match="filas"):
        parse_upload("x.csv", csv_bytes, s2)


def test_csv_delimiter_and_encoding(settings: Settings) -> None:
    text = "#;USUARIO;REGIÓN\n1;ard;Xalapa\n".encode("latin-1")
    parsed = parse_upload("x.csv", text, settings)
    assert parsed.columns == ["#", "USUARIO", "REGION"]
    assert parsed.rows[0]["REGION"] == "Xalapa"


def test_helpers() -> None:
    assert normalize_header(" REGIÓN ") == "REGION"
    assert cell_to_text(None) is None
    assert cell_to_text("  ") is None
    assert cell_to_text(4.0) == "4"
    assert cell_to_text(True) == "1"
