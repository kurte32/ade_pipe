# Data model · Pipeline de Posibles Tiendas

Date: 11 October 2026 · Branch `ux-redesign` · **Audience:** engineers and L2 support · **When to read:** before a schema change or a support query · **Source of truth:** `backend/app/models.py` and the baseline migration.

Reference for support queries and schema changes. Source of truth: `backend/app/models.py` and
the baseline migration `backend/migrations/versions/1130828e690d_baseline.py`. Ledger tables and
row-level security are raw SQL in that migration; autogenerate never manages them.

## 1. Tables

### Catalogs (seeded by the migration; business values pending, see `IMPROVEMENT_BACKLOG.md`)

| Table | Key | Columns | Seed |
|---|---|---|---|
| `estatus` | `codigo` | `nombre`, `orden`, `terminal` | `sitio_prospectado` 1, `dueno_localizado` 2, `primera_visita` 3, `recepcion_documentos` 4, `descartado` 90 (terminal), `entregado` 91 (terminal, never assigned by code today) |
| `motivo_devolucion` | `codigo` | `nombre`, `activo` | `calidad_datos`, `contacto_invalido`, `medidas_inconsistentes`, `documento_ilegible`, `documento_incompleto`, `otro` |
| `catalogo_tipo_documento` | `id` | `nombre`, `requerido_en_estatus` (FK), `activo`, `orden` | `escritura_hipoteca`, `uso_de_suelo`, `identificacion_propietario`, `predial`, all required at `recepcion_documentos` |

### Sites and captures (RLS applies)

| Table | Key | Important columns |
|---|---|---|
| `sitio` | `id`; `origen_id` unique | `nombre`, `region`, `lat`, `lon`, `gps_texto`, `potencial`, `campos_capturados`, `campos_total`, `fecha_origen_utc`, `fecha_origen_texto`, `estatus` (FK), `coordinador_oid`, `usuario_codigo`, `devuelto`, `devolucion_motivo`, `devolucion_comentario`, `en_revision_admin`, `revision_detalle`, `vigente`, `carga_lote_id`, `actualizado_utc`, **`rowversion`** (ETag; SQLAlchemy `version_id_col`, so a stale update raises `StaleDataError` → 412) |
| `sitio_contacto` | `sitio_id` | `nombre`, `telefono`, `correo`, `notas`, `capturado_utc`, `coordinador_oid`. Personal data: excluded from Fabric mirroring |
| `sitio_visita` | `sitio_id` | `frente_m`, `fondo_m`, `area_m2`, `fecha_visita_utc`, `notas`, `coordinador_oid` |
| `sitio_archivo` | `id` uuid5(session) | `sitio_id`, `tipo` (`foto`/`documento`), `tipo_documento`, `nombre_original`, `content_type`, `bytes`, `paginas`, `sha256`, `ruta_blob`, `version`, `vigente`, `estado` (`publicado`/`purgado`), `subido_utc`, `purga_utc`, `purgado_utc`, `coordinador_oid` |
| `subida_sesion` | `id` uuid | `sitio_id`, `coordinador_oid`, `tipo`, `tipo_documento`, `bytes_total`, `tamano_parte`, `partes_total`, `partes_recibidas`, `sha256_esperado`, `blob_staging`, `estado` (`abierta`, `escaneando`, `publicada`, `rechazada`, `expirada`, `cancelada`), `motivo_rechazo`, `expira_utc` |

### Loads

| Table | Key | Important columns |
|---|---|---|
| `carga_lote` | `id` uuid | `archivo_nombre`, `hash`, `fecha_utc`, `estado` (`vista_previa`, `confirmado`, `cancelado`), `filas_total/ok/advertencia/error`, `confirmado_utc`, `filas_insertadas/actualizadas/revision` |
| `carga_fila_staging` | `id`; index `(lote_id, num_fila)` | `num_fila` (from 2), `origen_id`, `datos_*` (original and normalised JSON), `resultado` (`ok`/`advertencia`/`error`), `motivos` (JSON list of `{codigo, mensaje}`), `accion_prevista` (`insertar`/`actualizar`/`revision`/null), `decision_admin` (`aprobar`/`excluir`/null) |

### Identity, sync, notifications

| Table | Key | Important columns |
|---|---|---|
| `coordinador_equivalencia` | `usuario_codigo` (3 to 10 lowercase letters) | `correo`, `oid` (null until resolved), `nombre`, `activo`, `actualizado_utc` |
| `operacion_idempotente` | `(clave, usuario_oid)` | `ruta`, `hash_cuerpo`, `codigo_respuesta` (0 while in flight), `cuerpo_respuesta`, `creado_utc`. RLS applies; purged after 7 days |
| `notificacion_outbox` | `id` | `destinatario_oid`, `sitio_id`, `tipo` (`devolucion`), `cuerpo` (JSON, no contact data), `estado` (`pendiente`/`enviada`/`fallida`), `intentos`, `siguiente_intento_utc`, `ultimo_error` (exception type only), `creado_utc`, `enviada_utc`, `leida_utc`. RLS on `destinatario_oid` |

### Ledgers (append-only, `LEDGER = ON (APPEND_ONLY = ON)`; UPDATE and DELETE denied to the app role)

| Table | Columns |
|---|---|
| `sitio_estatus_historial` | `sitio_id`, `estatus_anterior`, `estatus_nuevo`, `tipo` (`avance`, `devolucion`, `descarte`, `reasignacion`, `carga`), `motivo`, `comentario`, `usuario_oid`, `fecha_utc`, `origen` (`pwa`, `admin`, `carga`) |
| `auditoria` | `fecha_utc`, `usuario_oid`, `rol`, `accion`, `entidad`, `entidad_id`, `ip`, `correlation_id`, `detalle` (JSON) |

## 2. Row-level security

Policy `rls.coordinador_policy` with filter and block predicates on `sitio`, `sitio_contacto`,
`sitio_visita`, `sitio_archivo`, `subida_sesion` (column `coordinador_oid`),
`notificacion_outbox` (`destinatario_oid`) and `operacion_idempotente` (`usuario_oid`):

```sql
WHERE @coordinador_oid = TRY_CAST(SESSION_CONTEXT(N'oid') AS uniqueidentifier)
   OR CAST(SESSION_CONTEXT(N'rol') AS nvarchar(20)) IN (N'Admin', N'Sistema')
   OR IS_ROLEMEMBER(N'db_owner') = 1
```

The API sets `oid` and `rol` with `sp_set_session_context` on every connection checkout and
clears them on check-in; jobs use the all-zero `SYSTEM_OID` with role `Sistema`. Not covered by
RLS (protected only by the route role): `carga_lote`, `carga_fila_staging`,
`coordinador_equivalencia`, catalogs, both ledgers. A new table that stores coordinator data must
get a `coordinador_oid` column, be added to the policy in a migration, and get a case in
`tests/integration/test_identity_and_rls.py` (CI runbook RB-05).

## 3. Grants

Role `pipeline_app_role` (the API identity is added by the migration from `DB_USER`): SELECT,
INSERT, UPDATE, DELETE on `dbo`; DENY UPDATE and DELETE on both ledgers; DENY everything on
`alembic_version`. `sa` (local) and the `PIPELINE-SQL-Admins-{env}` group (Azure) bypass RLS as
`db_owner`, which is why support queries as an admin see every row.

## 4. Lifecycles at a glance

```text
Site:        sitio_prospectado -> dueno_localizado -> primera_visita -> recepcion_documentos
             any non-terminal  -> descartado (admin)      devolver: back to an earlier stage, devuelto=1
             devuelto cleared by the next successful avance; en_revision_admin set by a discard
             proposal or a load conflict, cleared by devolver / descartar / reasignar
Upload:      abierta -> (completar) -> publicada | escaneando -> publicada | rechazada
             abierta/escaneando past expira_utc -> expirada (job expire_uploads)
Document:    publicado (vigente) -> replaced: vigente=0, new row version+1
             publicado -> purgado after purga_utc (job purge; metadata kept)
Load:        vista_previa -> confirmado | cancelado
Outbox:      pendiente -> enviada | fallida (8 attempts, backoff min(2^n min, 6 h))
Idempotency: in flight (codigo_respuesta=0) -> stored response -> deleted after 7 days
```

## 5. Useful support queries (run as `sa` locally or the SQL admin group in Azure)

```sql
-- Where is a site and who owns it
SELECT id, origen_id, nombre, estatus, devuelto, en_revision_admin, vigente, usuario_codigo, coordinador_oid, actualizado_utc
FROM sitio WHERE origen_id = 566;

-- Its history and the audit rows of the last day
SELECT fecha_utc, tipo, estatus_anterior, estatus_nuevo, motivo, comentario, origen FROM sitio_estatus_historial WHERE sitio_id = 1 ORDER BY fecha_utc;
SELECT fecha_utc, rol, accion, entidad, entidad_id, correlation_id FROM auditoria WHERE fecha_utc > DATEADD(day, -1, SYSUTCDATETIME()) ORDER BY fecha_utc DESC;

-- Find the request behind an error the user reported (they see "Referencia: <id>")
SELECT * FROM auditoria WHERE correlation_id = '<id>';

-- Uploads waiting for a scan, and files due for purge this month
SELECT id, sitio_id, estado, actualizado_utc, expira_utc FROM subida_sesion WHERE estado IN ('abierta','escaneando');
SELECT id, sitio_id, tipo_documento, purga_utc FROM sitio_archivo WHERE estado = 'publicado' AND purga_utc < DATEADD(day, 30, SYSUTCDATETIME());

-- Notifications that failed
SELECT id, destinatario_oid, intentos, ultimo_error, siguiente_intento_utc FROM notificacion_outbox WHERE estado = 'fallida';

-- Unresolved coordinator codes (loads with that USUARIO fail)
SELECT usuario_codigo, correo, activo FROM coordinador_equivalencia WHERE oid IS NULL;

-- What a coordinator sees (RLS as that user)
EXEC sp_set_session_context 'oid', 'a0000000-0000-4000-8000-000000000001';
EXEC sp_set_session_context 'rol', 'Coordinador';
SELECT COUNT(*) FROM sitio;  -- note: db_owner still bypasses the predicate; use the API for an exact view
```

## 6. Changing the schema

1. Edit `backend/app/models.py`.
2. `docker compose run --rm --no-deps --user $(id -u):$(id -g) -e HOME=/tmp -e DB_HOST=sqlserver api alembic revision --autogenerate -m "describe"`.
3. Review the revision: ledger tables, the RLS policy and grants never autogenerate; add raw SQL
   when a new table needs RLS or when a ledger column changes.
4. Keep it expand-and-contract: the previous image must run against the new schema, because
   production rollback is a traffic shift, never a downgrade (see `RELEASE_PROCESS.md`).
5. `make db-migrate`, then `make test` (the RLS integration tests must stay green).
