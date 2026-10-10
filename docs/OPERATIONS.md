# Operations guide

How the platform is observed, diagnosed and recovered. Targets and alert definitions come from
`architecture/PRODUCTION_READINESS.md`; this document is the hands-on counterpart.

## Health endpoints

| Endpoint | Meaning | Used by |
|---|---|---|
| `GET /healthz` | Process is up. No dependencies. | Container Apps liveness probe, Front Door health probe |
| `GET /readyz` | Database `SELECT 1` and both storage containers reachable. 503 with per-check detail when degraded. | Container Apps readiness and startup probes, `make health` |

## Logs

The API and the jobs write one JSON object per line to stderr (collected by Container Apps into
Log Analytics, or by `docker compose logs` locally). Every request line carries
`correlation_id` (also returned as the `X-Correlation-Id` response header and in every Problem
Details body), `route`, `method`, `status`, and `user` (a 16-character hash of the oid, never
the oid itself). Keys named `nombre`, `telefono`, `correo`, `name`, `phone`, `email`, `token`,
`authorization`, `password` or `body` are redacted by the logger before output.

Useful KQL (Log Analytics, table `ContainerAppConsoleLogs_CL`):

```kusto
ContainerAppConsoleLogs_CL
| where Log_s has "correlation_id" and Log_s has "<id from the user>"
| project TimeGenerated, Log_s
```

Local: `make logs`, or `docker compose logs api | grep <correlation_id>`.

## Background jobs

| Job | Schedule (Azure) | Local scheduler | What it does | Failure handling |
|---|---|---|---|---|
| `promote` | every minute | 15 s | Promotes uploads in `escaneando` once the malware scan result is available | Waits; logs a warning when a session waits longer than `SCAN_WAIT_SECONDS` |
| `outbox` | every minute | 20 s | Delivers Teams notifications | Exponential backoff, `fallida` after 8 attempts, error text stored without personal data |
| `expire_uploads` | every 10 min | 10 min | Expires abandoned upload sessions and deletes their staging blobs | Idempotent |
| `purge` | daily | hourly | Deletes documents past `purga_utc`, keeps metadata, audits as `Sistema` | Skips blobs protected by immutability or legal hold and logs them |
| `idempotency_cleanup` | daily | hourly | Deletes replay records older than `IDEMPOTENCY_TTL_DAYS` | Idempotent |

Run one manually: `make job-<name>` locally, `az containerapp job start --name <job>` in Azure.
Every job uses a `Sistema` session context, which the RLS predicate accepts.

## Runbooks

### RB-01 Sync failures reported by coordinators
1. Ask for the site name and the time. In the PWA the conflict panel shows the server message and the correlation id.
2. Search logs by `correlation_id`. A 412 means the server state changed (usually an admin return); the coordinator must discard or redo the local change. A 422 lists `faltantes` (missing requirements).
3. Repeated 401 after a day offline is expected: the SPA refresh token lifetime forces a new sign-in; the queue is preserved.

### RB-02 Upload stuck in `escaneando`
1. `SELECT id, estado, actualizado_utc FROM subida_sesion WHERE estado = 'escaneando'`.
2. In Azure check the staging blob's index tags (`Malware Scanning scan result`). Missing tag after 15 minutes: check the Defender for Storage plan and the Event Grid system topic.
3. Running `promote` manually re-evaluates. Sessions past `expira_utc` are expired by `expire_uploads`; the coordinator re-uploads.

### RB-03 Outbox backlog
1. `SELECT estado, COUNT(*) FROM notificacion_outbox GROUP BY estado`.
2. `fallida` rows have `ultimo_error`. Typical causes: Graph permission `TeamsActivity.Send` missing, Teams app not installed for the user, `TEAMS_APP_ID` unset.
3. In-app notices are unaffected; the coordinator still sees the return on next sync.

### RB-04 Defender flagged a file as malicious
The session is set to `rechazada`, the staging blob deleted, and `archivo_rechazado_malware` audited. Inform Seguridad with the audit row; the coordinator is told to obtain a clean copy.

### RB-05 RLS test fails in CI
Treat as a release blocker. The failing test names the table. Check that the migration added the predicate for any new table carrying `coordinador_oid` and that the service sets the session context.

### RB-06 Reassigning a coordinator
Admin web, site detail, "Reasignar". The previous coordinator's device removes the site on its next delta sync (`removed_ids`). Equivalence changes for bulk loads are made on the Equivalencias page.

### RB-07 Retention purge
Runs daily. Review `SELECT COUNT(*) FROM sitio_archivo WHERE estado = 'purgado' AND purgado_utc > DATEADD(day, -1, SYSUTCDATETIME())`. A legal hold on a blob makes the delete fail; the job logs `purge_skipped` with the blob path and tries again the next day.

### RB-08 Restoring the database
Azure: point-in-time restore of the Azure SQL database to a new database name, then swap the connection (Container App secret or Key Vault reference) and redeploy. Ledger tables keep their digests; verify with `sys.sp_verify_database_ledger` after restore. Local: `make reset && make up && make db-seed`.

### RB-09 Rolling back a release
Container Apps keeps the previous revision. `az containerapp revision activate --revision <previous>` then shift traffic 100 % to it. Migrations are expand-and-contract, so the previous revision runs against the new schema. Never run `alembic downgrade` in production without a restore point.

### RB-10 Rotating the dev identity provider key (local only)
`docker compose down && docker volume rm ade-pipeline_devidpkeys && make up`. Everyone signs in again.

## Backup and recovery

| Store | Mechanism | Local equivalent |
|---|---|---|
| Azure SQL | Automated backups with point-in-time restore, long-term retention configured in Bicep | Docker volume `sqldata`; `make reset` destroys it |
| Documents (ADLS Gen2) | Soft delete, versioning, immutability policy; geo-redundant storage | Azurite volume `azuritedata` |
| Staging | Transient; lifecycle deletes after 7 days | same |
| Audit ledger | Append-only; digests can be stored externally (not configured in this build) | same table type in SQL Server 2022 |

Restore drill: documented in `architecture/PRODUCTION_READINESS.md` section 5; not executed in this build because no Azure environment exists.

## Alerts to configure (Azure Monitor)

Readiness probe failures, HTTP 5xx rate above 1 % over 5 minutes, `promote` sessions waiting over `SCAN_WAIT_SECONDS`, outbox `fallida` count increasing, purge job failures, SQL DTU/vCore above 80 %, and any `unhandled_error` log event. Exact thresholds and routing are in `architecture/PRODUCTION_READINESS.md`.
