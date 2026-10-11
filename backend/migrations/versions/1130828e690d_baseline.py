"""baseline

Revision ID: 1130828e690d
Revises:
Create Date: 2026-10-10 18:23:56.837332
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

revision = "1130828e690d"
down_revision = None
branch_labels = None
depends_on = None

APP_DB_USER = os.environ.get("DB_USER", "pipeline_app")

RAW_UPGRADE = [
    # rowversion is a system column (not emitted by SQLAlchemy DDL); used as ETag for If-Match.
    "ALTER TABLE dbo.sitio ADD rowversion rowversion NOT NULL",
    # Append-only ledger tables (ADR-009). UPDATE and DELETE are rejected by the engine.
    """
    CREATE TABLE dbo.sitio_estatus_historial (
        id bigint IDENTITY(1,1) NOT NULL CONSTRAINT pk_sitio_estatus_historial PRIMARY KEY,
        sitio_id int NOT NULL,
        estatus_anterior nvarchar(40) NULL,
        estatus_nuevo nvarchar(40) NOT NULL,
        tipo nvarchar(12) NOT NULL,
        motivo nvarchar(40) NULL,
        comentario nvarchar(1000) NULL,
        usuario_oid uniqueidentifier NOT NULL,
        fecha_utc datetime2(3) NOT NULL,
        origen nvarchar(10) NOT NULL
    ) WITH (SYSTEM_VERSIONING = OFF, LEDGER = ON (APPEND_ONLY = ON))
    """,
    "CREATE INDEX ix_hist_sitio ON dbo.sitio_estatus_historial (sitio_id, fecha_utc)",
    """
    CREATE TABLE dbo.auditoria (
        id bigint IDENTITY(1,1) NOT NULL CONSTRAINT pk_auditoria PRIMARY KEY,
        fecha_utc datetime2(3) NOT NULL,
        usuario_oid uniqueidentifier NOT NULL,
        rol nvarchar(20) NOT NULL,
        accion nvarchar(60) NOT NULL,
        entidad nvarchar(40) NOT NULL,
        entidad_id nvarchar(60) NOT NULL,
        ip nvarchar(45) NULL,
        correlation_id nvarchar(64) NULL,
        detalle nvarchar(max) NULL
    ) WITH (SYSTEM_VERSIONING = OFF, LEDGER = ON (APPEND_ONLY = ON))
    """,
    "CREATE INDEX ix_auditoria_fecha ON dbo.auditoria (fecha_utc)",
    "CREATE INDEX ix_auditoria_usuario ON dbo.auditoria (usuario_oid, fecha_utc)",
    "CREATE INDEX ix_auditoria_entidad ON dbo.auditoria (entidad, entidad_id)",
    # Row-Level Security (TDD 5.2, TO_BE 5). Admin and Sistema bypass by role; db_owner for maintenance.
    "CREATE SCHEMA rls",
    """
    CREATE FUNCTION rls.fn_coordinador_predicate(@coordinador_oid uniqueidentifier)
    RETURNS TABLE WITH SCHEMABINDING AS
    RETURN SELECT 1 AS ok
    WHERE @coordinador_oid = TRY_CAST(SESSION_CONTEXT(N'oid') AS uniqueidentifier)
       OR CAST(SESSION_CONTEXT(N'rol') AS nvarchar(20)) IN (N'Admin', N'Sistema')
       OR IS_ROLEMEMBER(N'db_owner') = 1
    """,
    """
    CREATE SECURITY POLICY rls.coordinador_policy
        ADD FILTER PREDICATE rls.fn_coordinador_predicate(coordinador_oid) ON dbo.sitio,
        ADD BLOCK  PREDICATE rls.fn_coordinador_predicate(coordinador_oid) ON dbo.sitio,
        ADD FILTER PREDICATE rls.fn_coordinador_predicate(coordinador_oid) ON dbo.sitio_contacto,
        ADD BLOCK  PREDICATE rls.fn_coordinador_predicate(coordinador_oid) ON dbo.sitio_contacto,
        ADD FILTER PREDICATE rls.fn_coordinador_predicate(coordinador_oid) ON dbo.sitio_visita,
        ADD BLOCK  PREDICATE rls.fn_coordinador_predicate(coordinador_oid) ON dbo.sitio_visita,
        ADD FILTER PREDICATE rls.fn_coordinador_predicate(coordinador_oid) ON dbo.sitio_archivo,
        ADD BLOCK  PREDICATE rls.fn_coordinador_predicate(coordinador_oid) ON dbo.sitio_archivo,
        ADD FILTER PREDICATE rls.fn_coordinador_predicate(coordinador_oid) ON dbo.subida_sesion,
        ADD BLOCK  PREDICATE rls.fn_coordinador_predicate(coordinador_oid) ON dbo.subida_sesion,
        ADD FILTER PREDICATE rls.fn_coordinador_predicate(destinatario_oid) ON dbo.notificacion_outbox,
        ADD BLOCK  PREDICATE rls.fn_coordinador_predicate(destinatario_oid) ON dbo.notificacion_outbox,
        ADD FILTER PREDICATE rls.fn_coordinador_predicate(usuario_oid) ON dbo.operacion_idempotente,
        ADD BLOCK  PREDICATE rls.fn_coordinador_predicate(usuario_oid) ON dbo.operacion_idempotente
    WITH (STATE = ON, SCHEMABINDING = ON)
    """,
    # Least-privilege application role: data access only, no DDL, no policy changes, no ledger edits.
    "IF DATABASE_PRINCIPAL_ID(N'pipeline_app_role') IS NULL CREATE ROLE pipeline_app_role",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::dbo TO pipeline_app_role",
    "DENY UPDATE, DELETE ON dbo.auditoria TO pipeline_app_role",
    "DENY UPDATE, DELETE ON dbo.sitio_estatus_historial TO pipeline_app_role",
    "DENY SELECT, INSERT, UPDATE, DELETE ON dbo.alembic_version TO pipeline_app_role",
    # Catalogs
    """
    INSERT INTO dbo.estatus (codigo, nombre, orden, terminal) VALUES
      (N'sitio_prospectado', N'Sitio Prospectado', 1, 0),
      (N'dueno_localizado', N'Dueño Localizado', 2, 0),
      (N'primera_visita', N'Primera visita', 3, 0),
      (N'recepcion_documentos', N'Recepción de documentos', 4, 0),
      (N'descartado', N'Descartado', 90, 1),
      (N'entregado', N'Entregado', 91, 1)
    """,
    """
    INSERT INTO dbo.motivo_devolucion (codigo, nombre, activo) VALUES
      (N'calidad_datos', N'Calidad de datos insuficiente', 1),
      (N'contacto_invalido', N'Datos de contacto no válidos', 1),
      (N'medidas_inconsistentes', N'Medidas inconsistentes', 1),
      (N'documento_ilegible', N'Documento ilegible', 1),
      (N'documento_incompleto', N'Documento incompleto o incorrecto', 1),
      (N'otro', N'Otro (ver comentario)', 1)
    """,
    # Provisional catalog: the four required documents are TDD pendiente 4.
    """
    INSERT INTO dbo.catalogo_tipo_documento (id, nombre, requerido_en_estatus, activo, orden) VALUES
      (N'escritura_hipoteca', N'Escritura o hipoteca', N'recepcion_documentos', 1, 1),
      (N'uso_de_suelo', N'Uso de suelo', N'recepcion_documentos', 1, 2),
      (N'identificacion_propietario', N'Identificación del propietario', N'recepcion_documentos', 1, 3),
      (N'predial', N'Boleta predial', N'recepcion_documentos', 1, 4)
    """,
]

RAW_DOWNGRADE = [
    "IF EXISTS (SELECT 1 FROM sys.security_policies WHERE name = N'coordinador_policy') DROP SECURITY POLICY rls.coordinador_policy",
    "IF OBJECT_ID(N'rls.fn_coordinador_predicate') IS NOT NULL DROP FUNCTION rls.fn_coordinador_predicate",
    "IF SCHEMA_ID(N'rls') IS NOT NULL DROP SCHEMA rls",
    "IF OBJECT_ID(N'dbo.auditoria') IS NOT NULL DROP TABLE dbo.auditoria",
    "IF OBJECT_ID(N'dbo.sitio_estatus_historial') IS NOT NULL DROP TABLE dbo.sitio_estatus_historial",
]


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "carga_lote",
        sa.Column("id", mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column("archivo_nombre", sa.Unicode(length=260), nullable=False),
        sa.Column("hash", sa.CHAR(length=64), nullable=False),
        sa.Column("usuario_admin", mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column("fecha_utc", sa.DateTime(), nullable=False),
        sa.Column("filas_total", sa.Integer(), nullable=False),
        sa.Column("filas_ok", sa.Integer(), nullable=False),
        sa.Column("filas_advertencia", sa.Integer(), nullable=False),
        sa.Column("filas_error", sa.Integer(), nullable=False),
        sa.Column("estado", sa.Unicode(length=20), nullable=False),
        sa.Column("confirmado_utc", sa.DateTime(), nullable=True),
        sa.Column("filas_insertadas", sa.Integer(), nullable=True),
        sa.Column("filas_actualizadas", sa.Integer(), nullable=True),
        sa.Column("filas_revision", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "coordinador_equivalencia",
        sa.Column("usuario_codigo", sa.Unicode(length=10), nullable=False),
        sa.Column("correo", sa.Unicode(length=200), nullable=False),
        sa.Column("oid", mssql.UNIQUEIDENTIFIER(), nullable=True),
        sa.Column("nombre", sa.Unicode(length=200), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("actualizado_por", mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column("actualizado_utc", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("usuario_codigo"),
    )
    op.create_table(
        "estatus",
        sa.Column("codigo", sa.Unicode(length=40), nullable=False),
        sa.Column("nombre", sa.Unicode(length=80), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("terminal", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("codigo"),
    )
    op.create_table(
        "motivo_devolucion",
        sa.Column("codigo", sa.Unicode(length=40), nullable=False),
        sa.Column("nombre", sa.Unicode(length=120), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("codigo"),
    )
    op.create_table(
        "operacion_idempotente",
        sa.Column("clave", sa.Unicode(length=80), nullable=False),
        sa.Column("usuario_oid", mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column("ruta", sa.Unicode(length=200), nullable=False),
        sa.Column("hash_cuerpo", sa.CHAR(length=64), nullable=False),
        sa.Column("codigo_respuesta", sa.Integer(), nullable=False),
        sa.Column("cuerpo_respuesta", sa.UnicodeText(), nullable=False),
        sa.Column("creado_utc", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("clave", "usuario_oid"),
    )
    op.create_table(
        "carga_fila_staging",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("lote_id", mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column("num_fila", sa.Integer(), nullable=False),
        sa.Column("datos_originales", sa.UnicodeText(), nullable=False),
        sa.Column("datos_normalizados", sa.UnicodeText(), nullable=True),
        sa.Column("resultado", sa.Unicode(length=15), nullable=False),
        sa.Column("motivos", sa.UnicodeText(), nullable=False),
        sa.Column("decision_admin", sa.Unicode(length=10), nullable=True),
        sa.Column("decidido_por", mssql.UNIQUEIDENTIFIER(), nullable=True),
        sa.Column("decidido_utc", sa.DateTime(), nullable=True),
        sa.Column("origen_id", sa.Integer(), nullable=True),
        sa.Column("accion_prevista", sa.Unicode(length=12), nullable=True),
        sa.ForeignKeyConstraint(["lote_id"], ["carga_lote.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_carga_fila_lote", "carga_fila_staging", ["lote_id", "num_fila"], unique=False
    )
    op.create_table(
        "catalogo_tipo_documento",
        sa.Column("id", sa.Unicode(length=50), nullable=False),
        sa.Column("nombre", sa.Unicode(length=120), nullable=False),
        sa.Column("requerido_en_estatus", sa.Unicode(length=40), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["requerido_en_estatus"],
            ["estatus.codigo"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sitio",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("origen_id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.Unicode(length=200), nullable=False),
        sa.Column("region", sa.Unicode(length=100), nullable=False),
        sa.Column("lat", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("lon", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("gps_texto", sa.Unicode(length=50), nullable=True),
        sa.Column("potencial", sa.Unicode(length=20), nullable=False),
        sa.Column("campos_capturados", sa.Integer(), nullable=False),
        sa.Column("campos_total", sa.Integer(), nullable=False),
        sa.Column("fecha_origen_utc", sa.DateTime(), nullable=False),
        sa.Column("fecha_origen_texto", sa.Unicode(length=40), nullable=False),
        sa.Column("estatus", sa.Unicode(length=40), nullable=False),
        sa.Column("coordinador_oid", mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column("usuario_codigo", sa.Unicode(length=10), nullable=False),
        sa.Column("devuelto", sa.Boolean(), nullable=False),
        sa.Column("devolucion_motivo", sa.Unicode(length=40), nullable=True),
        sa.Column("devolucion_comentario", sa.Unicode(length=1000), nullable=True),
        sa.Column("en_revision_admin", sa.Boolean(), nullable=False),
        sa.Column("revision_detalle", sa.Unicode(length=400), nullable=True),
        sa.Column("vigente", sa.Boolean(), nullable=False),
        sa.Column("carga_lote_id", mssql.UNIQUEIDENTIFIER(), nullable=True),
        sa.Column("creado_utc", sa.DateTime(), nullable=False),
        sa.Column("actualizado_utc", sa.DateTime(), nullable=False),
        sa.Column("rowversion", mssql.TIMESTAMP(), nullable=False, system=True),
        sa.ForeignKeyConstraint(
            ["carga_lote_id"],
            ["carga_lote.id"],
        ),
        sa.ForeignKeyConstraint(
            ["estatus"],
            ["estatus.codigo"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("origen_id"),
    )
    op.create_index("ix_sitio_coordinador", "sitio", ["coordinador_oid", "vigente"], unique=False)
    op.create_index("ix_sitio_estatus", "sitio", ["estatus"], unique=False)
    op.create_table(
        "notificacion_outbox",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("sitio_id", sa.Integer(), nullable=False),
        sa.Column("destinatario_oid", mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column("tipo", sa.Unicode(length=30), nullable=False),
        sa.Column("cuerpo", sa.UnicodeText(), nullable=False),
        sa.Column("intentos", sa.Integer(), nullable=False),
        sa.Column("estado", sa.Unicode(length=12), nullable=False),
        sa.Column("siguiente_intento_utc", sa.DateTime(), nullable=False),
        sa.Column("enviada_utc", sa.DateTime(), nullable=True),
        sa.Column("ultimo_error", sa.Unicode(length=400), nullable=True),
        sa.Column("leida_utc", sa.DateTime(), nullable=True),
        sa.Column("creado_utc", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["sitio_id"],
            ["sitio.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sitio_archivo",
        sa.Column("id", mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column("sitio_id", sa.Integer(), nullable=False),
        sa.Column("coordinador_oid", mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column("tipo", sa.Unicode(length=10), nullable=False),
        sa.Column("tipo_documento", sa.Unicode(length=50), nullable=True),
        sa.Column("nombre_original", sa.Unicode(length=260), nullable=False),
        sa.Column("content_type", sa.Unicode(length=100), nullable=False),
        sa.Column("ruta_blob", sa.Unicode(length=400), nullable=False),
        sa.Column("sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("paginas", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("vigente", sa.Boolean(), nullable=False),
        sa.Column("estado", sa.Unicode(length=12), nullable=False),
        sa.Column("subido_por", mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column("subido_utc", sa.DateTime(), nullable=False),
        sa.Column("purga_utc", sa.DateTime(), nullable=True),
        sa.Column("purgado_utc", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["sitio_id"],
            ["sitio.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tipo_documento"],
            ["catalogo_tipo_documento.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sitio_archivo_sitio", "sitio_archivo", ["sitio_id", "tipo", "vigente"], unique=False
    )
    op.create_table(
        "sitio_contacto",
        sa.Column("sitio_id", sa.Integer(), nullable=False),
        sa.Column("coordinador_oid", mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column("nombre", sa.Unicode(length=200), nullable=False),
        sa.Column("telefono", sa.Unicode(length=30), nullable=False),
        sa.Column("correo", sa.Unicode(length=200), nullable=True),
        sa.Column("notas", sa.Unicode(length=1000), nullable=True),
        sa.Column("capturado_por", mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column("capturado_utc", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["sitio_id"],
            ["sitio.id"],
        ),
        sa.PrimaryKeyConstraint("sitio_id"),
    )
    op.create_table(
        "sitio_visita",
        sa.Column("sitio_id", sa.Integer(), nullable=False),
        sa.Column("coordinador_oid", mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column("frente_m", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("fondo_m", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("area_m2", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("notas", sa.Unicode(length=1000), nullable=True),
        sa.Column("fecha_visita_utc", sa.DateTime(), nullable=False),
        sa.Column("capturado_por", mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column("capturado_utc", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["sitio_id"],
            ["sitio.id"],
        ),
        sa.PrimaryKeyConstraint("sitio_id"),
    )
    op.create_table(
        "subida_sesion",
        sa.Column("id", mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column("sitio_id", sa.Integer(), nullable=False),
        sa.Column("coordinador_oid", mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column("tipo", sa.Unicode(length=10), nullable=False),
        sa.Column("tipo_documento", sa.Unicode(length=50), nullable=True),
        sa.Column("nombre_original", sa.Unicode(length=260), nullable=False),
        sa.Column("content_type", sa.Unicode(length=100), nullable=False),
        sa.Column("bytes_total", sa.BigInteger(), nullable=False),
        sa.Column("tamano_parte", sa.Integer(), nullable=False),
        sa.Column("partes_total", sa.Integer(), nullable=False),
        sa.Column("sha256_esperado", sa.CHAR(length=64), nullable=False),
        sa.Column("sha256_real", sa.CHAR(length=64), nullable=True),
        sa.Column("estado", sa.Unicode(length=12), nullable=False),
        sa.Column("motivo_rechazo", sa.Unicode(length=400), nullable=True),
        sa.Column("blob_staging", sa.Unicode(length=400), nullable=False),
        sa.Column("paginas", sa.Integer(), nullable=True),
        sa.Column("archivo_id", mssql.UNIQUEIDENTIFIER(), nullable=True),
        sa.Column("creado_utc", sa.DateTime(), nullable=False),
        sa.Column("actualizado_utc", sa.DateTime(), nullable=False),
        sa.Column("expira_utc", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["sitio_id"],
            ["sitio.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # ---- hand-written: ledger tables, RLS, role and grants, catalogs ----
    for stmt in RAW_UPGRADE:
        op.execute(sa.text(stmt))
    op.execute(
        sa.text(
            f"IF DATABASE_PRINCIPAL_ID(N'{APP_DB_USER}') IS NOT NULL ALTER ROLE pipeline_app_role ADD MEMBER [{APP_DB_USER}]"
        )
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    for stmt in RAW_DOWNGRADE:
        op.execute(sa.text(stmt))
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("subida_sesion")
    op.drop_table("sitio_visita")
    op.drop_table("sitio_contacto")
    op.drop_index("ix_sitio_archivo_sitio", table_name="sitio_archivo")
    op.drop_table("sitio_archivo")
    op.drop_table("notificacion_outbox")
    op.drop_index("ix_sitio_estatus", table_name="sitio")
    op.drop_index("ix_sitio_coordinador", table_name="sitio")
    op.drop_table("sitio")
    op.drop_table("catalogo_tipo_documento")
    op.drop_index("ix_carga_fila_lote", table_name="carga_fila_staging")
    op.drop_table("carga_fila_staging")
    op.drop_table("operacion_idempotente")
    op.drop_table("motivo_devolucion")
    op.drop_table("estatus")
    op.drop_table("coordinador_equivalencia")
    op.drop_table("carga_lote")
    # ### end Alembic commands ###
