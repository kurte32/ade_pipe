"""datetime2(3) on every business timestamp

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-11 18:30:00
"""

from __future__ import annotations

from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None

# (table, column, nullable). Business tables used `datetime` (3.33 ms, rounds to .000/.003/.007)
# while the ledgers use datetime2(3) (audit DAT-14); one precision everywhere, lossless upgrade.
COLUMNS = [
    ("coordinador_equivalencia", "actualizado_utc", False),
    ("carga_lote", "fecha_utc", False),
    ("carga_lote", "confirmado_utc", True),
    ("carga_fila_staging", "decidido_utc", True),
    ("sitio", "fecha_origen_utc", False),
    ("sitio", "creado_utc", False),
    ("sitio", "actualizado_utc", False),
    ("sitio_contacto", "capturado_utc", False),
    ("sitio_visita", "fecha_visita_utc", False),
    ("sitio_visita", "capturado_utc", False),
    ("sitio_archivo", "subido_utc", False),
    ("sitio_archivo", "purga_utc", True),
    ("sitio_archivo", "purgado_utc", True),
    ("subida_sesion", "creado_utc", False),
    ("subida_sesion", "actualizado_utc", False),
    ("subida_sesion", "expira_utc", False),
    ("notificacion_outbox", "siguiente_intento_utc", False),
    ("notificacion_outbox", "enviada_utc", True),
    ("notificacion_outbox", "leida_utc", True),
    ("notificacion_outbox", "creado_utc", False),
    ("operacion_idempotente", "creado_utc", False),
]


def upgrade() -> None:
    for table, column, nullable in COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} DATETIME2(3) {'NULL' if nullable else 'NOT NULL'}"
        )


def downgrade() -> None:
    for table, column, nullable in reversed(COLUMNS):
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} DATETIME {'NULL' if nullable else 'NOT NULL'}"
        )
