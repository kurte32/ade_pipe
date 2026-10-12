"""integrity: one current document per type

Revision ID: b7c2e4a1d9f0
Revises: 1130828e690d
Create Date: 2026-10-11 16:10:00
"""

from __future__ import annotations

from alembic import op

revision = "b7c2e4a1d9f0"
down_revision = "1130828e690d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Filtered unique index: concurrent completes of the same document type used to leave several
    # vigente copies with the same version (audit DAT-3). Existing duplicates, if any, must be
    # retired first (the newest copy wins); the migration does that so it can never fail.
    op.execute(
        """
        UPDATE a SET vigente = 0
        FROM sitio_archivo a
        JOIN (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY sitio_id, tipo_documento ORDER BY subido_utc DESC, id DESC
            ) AS rn
            FROM sitio_archivo
            WHERE vigente = 1 AND tipo = 'documento'
        ) d ON d.id = a.id
        WHERE d.rn > 1
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_sitio_archivo_documento_vigente ON sitio_archivo (sitio_id, "
        "tipo_documento) WHERE vigente = 1 AND tipo = 'documento'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ux_sitio_archivo_documento_vigente ON sitio_archivo")
