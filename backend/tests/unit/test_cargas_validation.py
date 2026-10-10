from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.core.config import Settings
from app.models import ESTATUS_DUENO, ESTATUS_PROSPECTADO
from app.modules.cargas.validation import (
    ACCION_ACTUALIZAR,
    ACCION_INSERTAR,
    ACCION_REVISION,
    REQUIRED_COLUMNS,
    EquivalenciaRef,
    ExistingSite,
    MissingColumnsError,
    neutralize,
    parse_fecha,
    validate_rows,
)

OID_A = uuid.UUID("a0000000-0000-4000-8000-000000000001")
OID_B = uuid.UUID("a0000000-0000-4000-8000-000000000008")
EQ = {"ard": EquivalenciaRef("ard", OID_A), "usa": EquivalenciaRef("usa", OID_B)}


@pytest.fixture
def settings() -> Settings:
    return Settings(auth_tenant_id="t", auth_audience="a", auth_issuer="i", auth_jwks_url="j")


def row(**over: str | None) -> dict[str, str | None]:
    base: dict[str, str | None] = {
        "#": "560",
        "USUARIO": "ard",
        "REGION": "Xalapa",
        "SITIO": "Av. Uno 10",
        "COORDENADAS": "19.53, -96.92",
        "GPS": None,
        "POTENCIAL": "Alto",
        "CAMPOS": "24/24",
        "FECHA": "09/18/2026 14:37:02",
    }
    base.update(over)
    return base


def run(settings: Settings, rows: list[dict[str, str | None]], **kw):  # type: ignore[no-untyped-def]
    return validate_rows(
        REQUIRED_COLUMNS,
        rows,
        settings,
        equivalencias=kw.get("eq", EQ),
        existing=kw.get("existing", {}),
        existing_coords=kw.get("coords", []),
    )


def codes(res) -> set[str]:  # type: ignore[no-untyped-def]
    return {m["codigo"] for m in res.motivos}


def test_ok_row(settings: Settings) -> None:
    r = run(settings, [row()])[0]
    assert r.resultado == "ok" and r.accion_prevista == ACCION_INSERTAR
    n = r.normalizado
    assert n and n["coordinador_oid"] == str(OID_A) and n["lat"] == "19.530000"
    assert n["campos_capturados"] == 24 and n["fecha_origen_texto"] == "09/18/2026 14:37:02"


def test_missing_columns(settings: Settings) -> None:
    with pytest.raises(MissingColumnsError) as e:
        validate_rows(
            ["#", "USUARIO"], [], settings, equivalencias=EQ, existing={}, existing_coords=[]
        )
    assert "FECHA" in e.value.missing


@pytest.mark.parametrize(
    ("over", "code"),
    [
        ({"#": None}, "id_vacio"),
        ({"#": "abc"}, "id_no_numerico"),
        ({"USUARIO": "zzz"}, "usuario_sin_equivalencia"),
        ({"USUARIO": None}, "usuario_vacio"),
        ({"REGION": None}, "region_vacia"),
        ({"SITIO": None}, "sitio_vacio"),
        ({"COORDENADAS": "19.53"}, "coordenadas_formato"),
        ({"COORDENADAS": "45.0, -96.9"}, "coordenadas_fuera_rango"),
        ({"POTENCIAL": "Altísimo"}, "potencial_invalido"),
        ({"CAMPOS": "24"}, "campos_formato"),
        ({"CAMPOS": "25/24"}, "campos_formato"),
        ({"FECHA": "18/09/2026 14:37"}, "fecha_formato"),
    ],
)
def test_error_rules(settings: Settings, over: dict[str, str | None], code: str) -> None:
    r = run(settings, [row(**over)])[0]
    assert r.resultado == "error" and code in codes(r) and r.accion_prevista is None


def test_duplicate_id_in_file(settings: Settings) -> None:
    rs = run(settings, [row(), row(SITIO="Otro")])
    assert all(r.resultado == "error" and "id_repetido" in codes(r) for r in rs)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Prueba local 1", True),
        ("Ubicación por confirmar", True),
        ("Sitio VIABLE?", True),
        ("Av. Américas 5", False),
    ],
)
def test_suspicious_names(settings: Settings, name: str, expected: bool) -> None:
    r = run(settings, [row(SITIO=name)])[0]
    assert ("nombre_sospechoso" in codes(r)) is expected
    assert r.resultado == ("advertencia" if expected else "ok")


def test_campos_incompletos_warning(settings: Settings) -> None:
    r = run(settings, [row(CAMPOS="4/24")])[0]
    assert r.resultado == "advertencia" and "campos_incompletos" in codes(r)


def test_near_duplicates_in_file_and_existing(settings: Settings) -> None:
    rs = run(settings, [row(), row(**{"#": "561", "COORDENADAS": "19.53005, -96.92"})])
    assert all("coordenadas_cercanas" in codes(r) for r in rs)
    far = run(settings, [row(), row(**{"#": "561", "COORDENADAS": "19.54, -96.92"})])
    assert all("coordenadas_cercanas" not in codes(r) for r in far)
    vs_existing = run(settings, [row()], coords=[(99, 19.530001, -96.920001)])[0]
    assert "coordenadas_cercanas" in codes(vs_existing)
    # the existing site that IS this origen_id must not count as a duplicate of itself
    same = run(
        settings,
        [row()],
        existing={
            560: ExistingSite(
                99, 560, ESTATUS_PROSPECTADO, "ard", "Xalapa", "Av. Uno 10", 19.53, -96.92
            )
        },
        coords=[(99, 19.53, -96.92)],
    )[0]
    assert "coordenadas_cercanas" not in codes(same)


def test_gps_not_validated(settings: Settings) -> None:
    for gps in (None, "0", "3240", "7.5", "texto"):
        r = run(settings, [row(GPS=gps)])[0]
        assert r.resultado == "ok" and (r.normalizado or {})["gps_texto"] == gps


def test_formula_neutralization(settings: Settings) -> None:
    assert neutralize("=SUM(A1)") == "'=SUM(A1)"
    assert neutralize("+1") == "'+1" and neutralize("@x") == "'@x" and neutralize("-5") == "'-5"
    assert neutralize("Av. Uno") == "Av. Uno" and neutralize(None) is None
    r = run(settings, [row(SITIO="=HYPERLINK(1)")])[0]
    assert r.originales["SITIO"] == "'=HYPERLINK(1)"
    assert (r.normalizado or {})["nombre"] == "=HYPERLINK(1)"


def test_dates_two_formats_and_timezone() -> None:
    # Mexico City is UTC-6 all year (no DST since 2022)
    assert parse_fecha("09/18/2026 14:37:02") == datetime(2026, 9, 18, 20, 37, 2)
    assert parse_fecha("2026-09-18T14:37:02") == datetime(2026, 9, 18, 20, 37, 2)
    assert parse_fecha("2026-09-18T14:37:02Z") == datetime(2026, 9, 18, 14, 37, 2)
    assert parse_fecha("2026-09-18T14:37:02-05:00") == datetime(2026, 9, 18, 19, 37, 2)
    assert parse_fecha("09/18/2026") == datetime(2026, 9, 18, 6, 0, 0)
    assert parse_fecha("18/09/2026 14:37:02") is None
    assert parse_fecha("") is None


def test_reload_update_same_user(settings: Settings) -> None:
    ex = {
        560: ExistingSite(1, 560, ESTATUS_PROSPECTADO, "ard", "Xalapa", "Av. Uno 10", 19.53, -96.92)
    }
    r = run(settings, [row(CAMPOS="20/24")], existing=ex, coords=[(1, 19.53, -96.92)])[0]
    assert r.accion_prevista == ACCION_ACTUALIZAR
    assert "coordenadas_cercanas" not in codes(r)


def test_reload_user_changed_prospectado_reassigns_with_warning(settings: Settings) -> None:
    ex = {
        560: ExistingSite(1, 560, ESTATUS_PROSPECTADO, "ard", "Xalapa", "Av. Uno 10", 19.53, -96.92)
    }
    r = run(settings, [row(USUARIO="usa")], existing=ex)[0]
    assert r.resultado == "advertencia" and "usuario_cambiado" in codes(r)
    assert r.accion_prevista == ACCION_ACTUALIZAR


def test_reload_user_changed_advanced_goes_to_revision(settings: Settings) -> None:
    ex = {560: ExistingSite(1, 560, ESTATUS_DUENO, "ard", "Xalapa", "Av. Uno 10", 19.53, -96.92)}
    r = run(settings, [row(USUARIO="usa")], existing=ex)[0]
    assert r.resultado == "advertencia" and "usuario_cambiado_sitio_avanzado" in codes(r)
    assert r.accion_prevista == ACCION_REVISION


def test_reload_region_or_name_changed_warns(settings: Settings) -> None:
    ex = {
        560: ExistingSite(1, 560, ESTATUS_PROSPECTADO, "ard", "Xalapa", "Av. Uno 10", 19.53, -96.92)
    }
    r = run(settings, [row(SITIO="Av. Uno 11")], existing=ex)[0]
    assert "datos_cambiados" in codes(r) and r.accion_prevista == ACCION_ACTUALIZAR
