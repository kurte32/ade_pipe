"""database checks for values the code assumes

Revision ID: c9d1e2f3a4b5
Revises: b7c2e4a1d9f0
Create Date: 2026-10-11 16:40:00
"""

from __future__ import annotations

from alembic import op

revision = "c9d1e2f3a4b5"
down_revision = "b7c2e4a1d9f0"
branch_labels = None
depends_on = None

# (table, constraint name, expression). Every value set was enforced only in Python (audit DAT-14).
CHECKS = [
    ("sitio_visita", "ck_sitio_visita_medidas", "frente_m > 0 AND fondo_m > 0"),
    ("sitio_archivo", "ck_sitio_archivo_tipo", "tipo IN ('foto', 'documento')"),
    ("sitio_archivo", "ck_sitio_archivo_estado", "estado IN ('publicado', 'purgado')"),
    ("sitio_archivo", "ck_sitio_archivo_version", "version >= 1"),
    ("subida_sesion", "ck_subida_sesion_tipo", "tipo IN ('foto', 'documento')"),
    (
        "subida_sesion",
        "ck_subida_sesion_estado",
        "estado IN ('abierta', 'escaneando', 'publicada', 'rechazada', 'expirada', 'cancelada')",
    ),
    ("carga_lote", "ck_carga_lote_estado", "estado IN ('vista_previa', 'confirmado', 'cancelado')"),
    (
        "carga_fila_staging",
        "ck_carga_fila_resultado",
        "resultado IN ('ok', 'advertencia', 'error')",
    ),
    (
        "notificacion_outbox",
        "ck_notificacion_outbox_estado",
        "estado IN ('pendiente', 'enviando', 'enviada', 'fallida')",
    ),
]


def upgrade() -> None:
    for table, name, expr in CHECKS:
        op.execute(f"ALTER TABLE {table} WITH CHECK ADD CONSTRAINT {name} CHECK ({expr})")
    op.create_foreign_key(
        "fk_subida_sesion_tipo_documento",
        "subida_sesion",
        "catalogo_tipo_documento",
        ["tipo_documento"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_subida_sesion_tipo_documento", "subida_sesion", type_="foreignkey")
    for table, name, _ in reversed(CHECKS):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
