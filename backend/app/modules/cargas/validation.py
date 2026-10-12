"""Row validation and reload semantics for bulk loads (TDD 8.3, 8.4, 8.5; Anexo A).

Pure functions: lookups (equivalences, existing sites) are injected so unit tests run without
a database.
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from app.core.clock import MEXICO_CITY, to_utc_naive
from app.core.config import Settings
from app.models import ESTATUS_PROSPECTADO

REQUIRED_COLUMNS = [
    "#",
    "USUARIO",
    "REGION",
    "SITIO",
    "COORDENADAS",
    "GPS",
    "POTENCIAL",
    "CAMPOS",
    "FECHA",
]
POTENCIALES = {"Muy alto", "Alto", "Medio", "Bajo", "Sin estatus"}
LAT_RANGE = (14.5, 32.8)
LON_RANGE = (-118.5, -86.5)
FORMULA_PREFIXES = ("=", "+", "-", "@")
DATE_FORMATS = ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y")

RESULT_OK = "ok"
RESULT_WARNING = "advertencia"
RESULT_ERROR = "error"
ACCION_INSERTAR = "insertar"
ACCION_ACTUALIZAR = "actualizar"
ACCION_REVISION = "revision"


class MissingColumnsError(Exception):
    def __init__(self, missing: list[str]) -> None:
        super().__init__(", ".join(missing))
        self.missing = missing


@dataclass
class EquivalenciaRef:
    usuario_codigo: str
    oid: UUID


@dataclass
class ExistingSite:
    id: int
    origen_id: int
    estatus: str
    usuario_codigo: str
    region: str
    nombre: str
    lat: float
    lon: float


@dataclass
class RowResult:
    num_fila: int
    resultado: str
    motivos: list[dict[str, str]] = field(default_factory=list)
    normalizado: dict[str, Any] | None = None
    origen_id: int | None = None
    accion_prevista: str | None = None
    originales: dict[str, str | None] = field(default_factory=dict)

    def add(self, resultado: str, codigo: str, mensaje: str) -> None:
        self.motivos.append({"codigo": codigo, "mensaje": mensaje, "nivel": resultado})
        if resultado == RESULT_ERROR or self.resultado != RESULT_ERROR:
            if resultado == RESULT_ERROR:
                self.resultado = RESULT_ERROR
            elif self.resultado == RESULT_OK:
                self.resultado = RESULT_WARNING


def fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch)).lower()


def neutralize(value: str | None) -> str | None:
    """Formula-injection guard for spreadsheet EXPORTS (TDD 8.1). Not applied on load: stored
    values must be the file's own (audit DAT-17); call this when writing cells to a file."""
    if value is None:
        return None
    if value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def parse_coords(text: str | None) -> tuple[Decimal, Decimal] | None:
    if not text:
        return None
    parts = [p.strip() for p in text.replace(";", ",").split(",")]
    if len(parts) != 2:
        return None
    try:
        lat, lon = Decimal(parts[0]), Decimal(parts[1])
    except InvalidOperation:
        return None
    return lat.quantize(Decimal("0.000001")), lon.quantize(Decimal("0.000001"))


def in_mexico(lat: Decimal, lon: Decimal) -> bool:
    return LAT_RANGE[0] <= float(lat) <= LAT_RANGE[1] and LON_RANGE[0] <= float(lon) <= LON_RANGE[1]


def parse_campos(text: str | None) -> tuple[int, int] | None:
    if not text or "/" not in text:
        return None
    a, b = text.split("/", 1)
    try:
        n, m = int(a.strip()), int(b.strip())
    except ValueError:
        return None
    if n < 0 or m <= 0 or n > m:
        return None
    return n, m


def parse_fecha(text: str | None) -> datetime | None:
    """ISO 8601 or mm/dd/yyyy [HH:MM[:SS]], local Mexico City unless an offset is present."""
    if not text:
        return None
    raw = text.strip()
    local: datetime | None = None
    try:
        local = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        for fmt in DATE_FORMATS:
            try:
                local = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
    if local is None:
        return None
    if local.tzinfo is None:
        local = local.replace(tzinfo=MEXICO_CITY)
    return to_utc_naive(local)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _cell(lat: float, lon: float) -> tuple[int, int]:
    return int(lat * 1000), int(lon * 1000)


class _Grid:
    """Bucketed neighbour search (~110 m cells) for near-duplicate detection."""

    def __init__(self) -> None:
        self.cells: dict[tuple[int, int], list[tuple[str, float, float]]] = {}

    def add(self, key: str, lat: float, lon: float) -> None:
        self.cells.setdefault(_cell(lat, lon), []).append((key, lat, lon))

    def near(self, lat: float, lon: float, meters: float, exclude: str) -> list[str]:
        cx, cy = _cell(lat, lon)
        hits: list[str] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for key, la, lo in self.cells.get((cx + dx, cy + dy), []):
                    if key != exclude and haversine_m(lat, lon, la, lo) <= meters:
                        hits.append(key)
        return hits


def validate_rows(
    columns: list[str],
    rows: list[dict[str, str | None]],
    settings: Settings,
    *,
    equivalencias: dict[str, EquivalenciaRef],
    existing: dict[int, ExistingSite],
    existing_coords: list[tuple[int, float, float]],
) -> list[RowResult]:
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise MissingColumnsError(missing)

    results: list[RowResult] = []
    seen_ids: dict[int, list[RowResult]] = {}
    grid = _Grid()
    for sid, la, lo in existing_coords:
        grid.add(f"sitio:{sid}", la, lo)
    suspicious = [fold(w) for w in settings.suspicious_words]

    for idx, row in enumerate(rows, start=2):  # row 1 is the header
        res = RowResult(num_fila=idx, resultado=RESULT_OK, originales=dict(row.items()))
        results.append(res)
        norm: dict[str, Any] = {}

        # --- # ---------------------------------------------------------------------------
        raw_id = (row.get("#") or "").strip()
        origen_id: int | None = None
        if not raw_id:
            res.add(RESULT_ERROR, "id_vacio", "La columna # está vacía.")
        elif not raw_id.lstrip("-").isdigit() or int(raw_id) <= 0:
            res.add(RESULT_ERROR, "id_no_numerico", "La columna # no es un entero positivo.")
        else:
            origen_id = int(raw_id)
            res.origen_id = origen_id
            norm["origen_id"] = origen_id
            seen_ids.setdefault(origen_id, []).append(res)

        # --- USUARIO ---------------------------------------------------------------------
        usuario = (row.get("USUARIO") or "").strip().lower()
        norm["usuario_codigo"] = usuario
        eq = equivalencias.get(usuario)
        if not usuario:
            res.add(RESULT_ERROR, "usuario_vacio", "USUARIO está vacío.")
        elif eq is None:
            res.add(
                RESULT_ERROR,
                "usuario_sin_equivalencia",
                f"USUARIO '{usuario}' no tiene equivalencia activa con cuenta de Entra.",
            )
        else:
            norm["coordinador_oid"] = str(eq.oid)

        # --- REGION, SITIO ---------------------------------------------------------------
        region = (row.get("REGION") or "").strip()
        nombre = (row.get("SITIO") or "").strip()
        norm["region"] = region
        norm["nombre"] = nombre
        if not region:
            res.add(RESULT_ERROR, "region_vacia", "REGIÓN está vacía.")
        if not nombre:
            res.add(RESULT_ERROR, "sitio_vacio", "SITIO está vacío.")
        else:
            folded = fold(nombre)
            hit = next((w for w in suspicious if w and w in folded), None)
            if hit:
                res.add(
                    RESULT_WARNING,
                    "nombre_sospechoso",
                    f"El nombre del sitio contiene la palabra '{hit}'.",
                )

        # --- COORDENADAS -----------------------------------------------------------------
        coords = parse_coords(row.get("COORDENADAS"))
        if coords is None:
            res.add(
                RESULT_ERROR, "coordenadas_formato", 'COORDENADAS debe tener el formato "lat, lon".'
            )
        elif not in_mexico(*coords):
            res.add(
                RESULT_ERROR, "coordenadas_fuera_rango", "COORDENADAS fuera del rango de México."
            )
        else:
            norm["lat"], norm["lon"] = str(coords[0]), str(coords[1])
            grid.add(f"fila:{idx}", float(coords[0]), float(coords[1]))

        # --- GPS (as-is) -----------------------------------------------------------------
        norm["gps_texto"] = (row.get("GPS") or "").strip() or None

        # --- POTENCIAL -------------------------------------------------------------------
        potencial = (row.get("POTENCIAL") or "").strip()
        norm["potencial"] = potencial
        if potencial not in POTENCIALES:
            res.add(
                RESULT_ERROR,
                "potencial_invalido",
                "POTENCIAL debe ser Muy alto, Alto, Medio, Bajo o Sin estatus.",
            )

        # --- CAMPOS ----------------------------------------------------------------------
        campos = parse_campos(row.get("CAMPOS"))
        if campos is None:
            res.add(RESULT_ERROR, "campos_formato", "CAMPOS debe tener el formato n/m.")
        else:
            norm["campos_capturados"], norm["campos_total"] = campos
            if campos[0] < campos[1]:
                res.add(
                    RESULT_WARNING,
                    "campos_incompletos",
                    f"CAMPOS incompletos ({campos[0]}/{campos[1]}).",
                )

        # --- FECHA -----------------------------------------------------------------------
        fecha_txt = (row.get("FECHA") or "").strip()
        fecha = parse_fecha(fecha_txt)
        if fecha is None:
            res.add(
                RESULT_ERROR,
                "fecha_formato",
                "FECHA no se reconoce (ISO 8601 o mes/día/año con hora).",
            )
        else:
            norm["fecha_origen_utc"] = fecha.isoformat()
            norm["fecha_origen_texto"] = fecha_txt[:40]

        res.normalizado = norm

    # --- duplicates of # inside the file -----------------------------------------------------
    for oid_, group in seen_ids.items():
        if len(group) > 1:
            for r in group:
                r.add(
                    RESULT_ERROR, "id_repetido", f"La columna # ({oid_}) se repite en el archivo."
                )

    # --- near duplicates and reload semantics ------------------------------------------------
    for res in results:
        norm = res.normalizado or {}
        if "lat" in norm:
            hits = grid.near(
                float(norm["lat"]),
                float(norm["lon"]),
                settings.duplicate_distance_meters,
                exclude=f"fila:{res.num_fila}",
            )
            prev_site = existing.get(res.origen_id) if res.origen_id is not None else None
            self_key = f"sitio:{prev_site.id}" if prev_site else ""
            hits = [h for h in hits if h != self_key]
            if hits:
                labels = ", ".join(
                    h.replace("fila:", "fila ").replace("sitio:", "sitio ") for h in hits[:5]
                )
                res.add(
                    RESULT_WARNING,
                    "coordenadas_cercanas",
                    f"Coordenadas a menos de {settings.duplicate_distance_meters:g} m de: "
                    f"{labels}.",
                )
        if res.resultado == RESULT_ERROR:
            res.accion_prevista = None
            continue
        prev = existing.get(res.origen_id) if res.origen_id is not None else None
        if prev is None:
            res.accion_prevista = ACCION_INSERTAR
            continue
        res.accion_prevista = ACCION_ACTUALIZAR
        if norm.get("usuario_codigo") != prev.usuario_codigo:
            if prev.estatus != ESTATUS_PROSPECTADO:
                res.accion_prevista = ACCION_REVISION
                res.add(
                    RESULT_WARNING,
                    "usuario_cambiado_sitio_avanzado",
                    f"USUARIO cambió de '{prev.usuario_codigo}' a '{norm.get('usuario_codigo')}' "
                    "en un sitio que ya avanzó. Al aprobar queda en revisión del administrador, "
                    "no se reasigna.",
                )
            else:
                res.add(
                    RESULT_WARNING,
                    "usuario_cambiado",
                    f"USUARIO cambió de '{prev.usuario_codigo}' a '{norm.get('usuario_codigo')}'. "
                    "Al aprobar se reasigna el sitio.",
                )
        if norm.get("region") != prev.region or norm.get("nombre") != prev.nombre:
            res.add(
                RESULT_WARNING,
                "datos_cambiados",
                "REGIÓN o SITIO cambiaron respecto al registro existente. "
                "Al aprobar se actualizan.",
            )
    return results
