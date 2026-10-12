"""let the application read the applied schema revision

Revision ID: d4e5f6a7b8c9
Revises: c9d1e2f3a4b5
Create Date: 2026-10-11 18:10:00
"""

from __future__ import annotations

from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c9d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The baseline denied every permission on alembic_version to the app role so the API can never
    # alter it. Reading it is harmless and lets /readyz report which schema revision is applied
    # (backlog D-03r). REVOKE removes the DENY for SELECT only; INSERT/UPDATE/DELETE stay denied.
    op.execute("REVOKE SELECT ON dbo.alembic_version FROM pipeline_app_role")
    op.execute("GRANT SELECT ON dbo.alembic_version TO pipeline_app_role")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON dbo.alembic_version FROM pipeline_app_role")
    op.execute("DENY SELECT ON dbo.alembic_version TO pipeline_app_role")
