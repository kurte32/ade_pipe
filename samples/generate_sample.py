"""Generate a SYNTHETIC load file matching TDD Anexo A.

The real file pipeline_nacional_mx_20261009.xlsx is not in the repository. This script
produces a file with the same shape: 87 rows, 9 columns, 10 user codes, two regions,
five suspicious names, GPS blanks/zeros/thousands, and mm/dd/yyyy HH:MM:SS dates.
All names and coordinates are invented.

Run: uv run --with openpyxl python samples/generate_sample.py
"""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).parent
random.seed(20261009)

USERS_XALAPA = ["ard", "mmi", "jjt", "jal", "ede", "cmc", "rsp"]
USERS_AZCA = ["usa", "bgl", "jdc"]
POTENCIAL = ["Sin estatus"] * 62 + ["Muy alto"] * 8 + ["Alto"] * 8 + ["Bajo"] * 5 + ["Medio"] * 4
random.shuffle(POTENCIAL)

STREETS = [
    "Av. Lázaro Cárdenas", "Calle Enríquez", "Av. Xalapa", "Av. 20 de Noviembre", "Calle Clavijero",
    "Av. Américas", "Circuito Presidentes", "Av. Ruiz Cortines", "Calle Úrsulo Galván", "Av. Orizaba",
    "Av. Azcapotzalco", "Calz. Vallejo", "Av. Cuitláhuac", "Av. Aquiles Serdán", "Calle Castilla",
    "Av. de las Granjas", "Eje 5 Norte", "Av. Tezozómoc", "Calle Hacienda del Rosario", "Av. Ceylán",
]
SUSPICIOUS = ["Prueba local 1", "Sitio viable?", "Equivocado borrar", "Ubicación por confirmar", "prueba"]


def coords(region: str) -> tuple[float, float]:
    if region == "Xalapa":
        return round(19.52 + random.uniform(-0.05, 0.05), 6), round(-96.92 + random.uniform(-0.05, 0.05), 6)
    return round(19.48 + random.uniform(-0.03, 0.03), 6), round(-99.18 + random.uniform(-0.03, 0.03), 6)


def main() -> None:
    rows: list[list[object]] = []
    ids = sorted(random.sample(range(560, 3290), 87))
    regions = ["Xalapa"] * 68 + ["Azcapotzalco"] * 19
    start = datetime(2026, 6, 13, 8, 0, 0)
    gps_pattern = ([None] * 10) + ([0] * 8) + ([random.randint(1000, 4000) for _ in range(9)]) + [
        round(random.uniform(3, 25), 1) for _ in range(60)
    ]
    random.shuffle(gps_pattern)
    campos_full = set(random.sample(range(87), 19))
    susp_idx = set(random.sample(range(87), 5))
    susp = list(SUSPICIOUS)
    for i in range(87):
        region = regions[i]
        user = random.choice(USERS_XALAPA if region == "Xalapa" else USERS_AZCA)
        lat, lon = coords(region)
        name = susp.pop() if i in susp_idx else f"{random.choice(STREETS)} {random.randint(10, 999)}"
        campos = 24 if i in campos_full else random.randint(2, 23)
        fecha = start + timedelta(days=random.randint(0, 117), minutes=random.randint(0, 600))
        rows.append([
            ids[i], user, region, name, f"{lat}, {lon}", gps_pattern[i], POTENCIAL[i],
            f"{campos}/24", fecha.strftime("%m/%d/%Y %H:%M:%S"),
        ])
    # one near-duplicate coordinate pair (warning rule, 15 m)
    rows[40][4] = rows[41][4]

    header = ["#", "USUARIO", "REGIÓN", "SITIO", "COORDENADAS", "GPS", "POTENCIAL", "CAMPOS", "FECHA"]
    wb = Workbook()
    ws = wb.active
    ws.title = "pipeline"
    ws.append(header)
    for r in rows:
        ws.append(r)
    wb.save(HERE / "pipeline_nacional_mx_20261009_SINTETICO.xlsx")
    with (HERE / "pipeline_nacional_mx_20261009_SINTETICO.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["#", "USUARIO", "REGION", "SITIO", "COORDENADAS", "GPS", "POTENCIAL", "CAMPOS", "FECHA"])
        for r in rows:
            w.writerow(["" if v is None else v for v in r])
    print(f"wrote {len(rows)} rows")


if __name__ == "__main__":
    main()
