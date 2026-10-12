# Operations guide

How the platform is observed, diagnosed and recovered. Targets and alert definitions come from
`architecture/PRODUCTION_READINESS.md`; this document is the hands-on counterpart.

## Health endpoints

| Endpoint | Meaning | Used by |
|---|---|---|
| `GET /healthz` | Process is up. No dependencies. | Container Apps liveness probe, Front Door health probe |
| `GET /readyz` | Database `SELECT 1`, the applied Alembic revision versus the code's head (`schema_revision`, `schema_head`, `schema`: `ok`, `behind` or `ahead-or-unknown`) and both storage containers reachable. 503 with per-check detail when degraded, including a database behind the code (a deployment that skipped the migrate job). | Container Apps readiness and startup probes, `make health` |

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
2. Search logs by `correlation_id` (or by `sitio_id`). A 412 means the server state changed (usually an admin return); the coordinator must discard or redo the local change. A 422 lists `faltantes` (missing requirements). A 429 is the per-user limit; it clears within a minute.
3. Repeated 401 after a day offline is expected: the SPA refresh token lifetime forces a new sign-in; the queue is preserved. Transient failures (5xx, timeouts) are retried with a growing backoff and never become terminal; "Sincronizar ahora" forces an attempt.
4. A diverged cache (the phone shows a state the server does not have): "Volver a descargar" on Mis sitios re-downloads every site and keeps the queued changes.

### RB-02 Upload stuck in `escaneando`
1. `SELECT id, estado, actualizado_utc FROM subida_sesion WHERE estado = 'escaneando'`.
2. In Azure check the staging blob's index tags (`Malware Scanning scan result`). Missing tag after 15 minutes: check the Defender for Storage plan and the Event Grid system topic.
3. Running `promote` manually re-evaluates. Sessions past `expira_utc` are expired by `expire_uploads`; the coordinator re-uploads.

### RB-03 Outbox backlog
1. `SELECT estado, COUNT(*) FROM notificacion_outbox GROUP BY estado`. `enviando` rows older than 15 minutes belong to a run that died; the next run releases them.
2. `fallida` rows have `ultimo_error` and a `notificacion_fallida` audit row. Typical causes: Graph permission `TeamsActivity.Send` missing, Teams app not installed for the user, `TEAMS_APP_ID` unset or `NOTIFY_MODE=log` (dev and test until the Teams app exists).
3. In-app notices are unaffected; the coordinator still sees the return on next sync. The alert `notifications-dead-lettered` fires on any `fallida` row in the last hour.

### RB-04 Defender flagged a file as malicious
The session is set to `rechazada`, the staging blob deleted, and `archivo_rechazado_malware` audited. Inform Seguridad with the audit row; the coordinator is told to obtain a clean copy.

### RB-05 RLS test fails in CI
Treat as a release blocker. The failing test names the table. Check that the migration added the predicate for any new table carrying `coordinador_oid` and that the service sets the session context.

### RB-06 Reassigning a coordinator
Admin web, site detail, "Reasignar" (only to a coordinator with an active equivalence). Contact, visit, files, open uploads and pending notices move with the site; the previous coordinator's device removes the site and its queued changes on its next delta sync (`removed_ids`) and shows how many changes were dropped. A bulk reload that changes `USUARIO` on a `sitio_prospectado` site does the same; on an advanced site it flags the site for review instead. Equivalence changes for bulk loads are made on the Equivalencias page.

### RB-07 Retention purge
Runs daily. Review `SELECT COUNT(*) FROM sitio_archivo WHERE estado = 'purgado' AND purgado_utc > DATEADD(day, -1, SYSUTCDATETIME())`. A legal hold or immutability policy makes the delete fail with 409 (403 for a missing permission): the job logs `purge_blocked`, writes a `purga_bloqueada` audit row and tries again the next day; the `purge-blocked` alert tells Legal. Any other storage error is `purge_failed` (alert `jobs-failed`) and is retried the next run.

### RB-08 Restoring the database
Azure: point-in-time restore of the Azure SQL database to a new database name, then repoint the API by updating the `DB_HOST`/`DB_NAME` container-app environment variables (they are plain env vars, not a Key Vault reference) and redeploy. Ledger tables keep their digests; external digest storage is not configured in this build, so `sys.sp_verify_database_ledger` validates only the in-database digest. Local: `make reset && make up && make db-seed`.

Verify the ledger on the restored copy before repointing (rehearsed locally on 11 October 2026):

```sql
ALTER DATABASE pipeline_restored SET ALLOW_SNAPSHOT_ISOLATION ON;  -- required by the verifier; Azure SQL has it on
EXEC sys.sp_generate_database_ledger_digest;                         -- one JSON row: database_name, block_id, hash, …
EXEC sys.sp_verify_database_ledger N'<that JSON row>';               -- raises on failure, returns silently on success
```

`sqlcmd` wraps long rows; run the two statements from Python through `app.core.db.build_engine(settings, admin=True, database="pipeline_restored")` or from the portal's query editor. Then confirm RLS on the copy: as the app login with no session context `SELECT COUNT(*) FROM sitio` is 0, and with `sp_set_session_context` for a coordinator it returns only their sites.

### RB-09 Rolling back a release
The container app runs in multiple-revision mode and keeps the previous revision active. A
deployment only shifts traffic after the migration job succeeded and the new revision is healthy,
and it restores the previous revision automatically if a later step fails. To roll back by hand,
`az containerapp ingress traffic set -g <rg> -n ca-pipeline-api-<env> --revision-weight <previous>=100`
moves all traffic back within seconds. Migrations are expand-and-contract, so the previous
revision runs against the new schema. Never run `alembic downgrade` in production without a
restore point. If the previous revision is gone, redeploy its image digest through `build-deploy`.

### RB-10 API outage (5xx rate, availability test, restarts)
1. `GET https://<host>/readyz` says which dependency is down; an administrator token on `GET /healthz/deps` adds JWKS and Graph with latency.
2. Azure portal: Container App revisions and replica status; `ContainerAppConsoleLogs_CL` filtered by `revision` and `status >= 500`; `ContainerAppSystemLogs_CL` for restarts and image pulls.
3. A bad release: RB-09 (traffic back to the previous revision). A database problem: RB-11. A Front Door or WAF problem: `FrontDoorAccessLog` / RB-13.

### RB-11 Database (failed connections, CPU, deadlocks)
1. Azure SQL metrics: CPU, DTU/vCore, failed connections, deadlocks; Query Performance Insight for the top statements.
2. The API's pool is 5 + 10 overflow per replica; `readyz` failing with `database: error` while the server is up points at the firewall (dev), the private endpoint DNS (test/prod) or the managed identity's database user (`DB_USER`, migrate job).
3. Scale the SKU (parameter file, redeploy) or restore (RB-08). Never change the schema by hand; RLS and ledgers are migration-managed.
4. While the database is unreachable the API answers 503 `service-unavailable` with `Retry-After: 10` and `/readyz` is 503; clients retry with backoff. It recovers on its own when the database returns (rehearsed locally: `/readyz` back to 200 within ~6 s, no restart).

### RB-12 Ingestion cost (Log Analytics daily cap)
1. The workspace stops ingesting at the cap (`logDailyCapGb`): alerts go blind until the next day. Check `Usage` by table; the API's request log is the usual driver.
2. Raise `LOG_LEVEL` to `WARNING` temporarily (parameter `logLevel`, redeploy) or raise the cap; retention is `logRetentionDays`.

### RB-13 WAF review (blocks above baseline)
1. `FrontDoorWebApplicationFirewallLog` by rule id, client IP and request URI. The 4 MB upload parts (`PUT /api/v1/subidas/*/partes/*`) are the first suspects for false positives on body inspection.
2. Confirm with the coordinator's correlation id (the chip shows the error). A false positive: add an exclusion for that rule on that path in `frontdoor-profile.bicep`, never switch the policy to Detection in production.
3. Real abuse: the per-IP rate limit (`rateLimitPerMinute`) and the API's per-user limits (429) already apply; report to Seguridad with the log.

### RB-14 Infrastructure drift
`drift.yml` runs nightly and reports every `Modify`/`Create`/`Delete` the templates would make. Review the what-if output: a manual portal change is reverted by the next deployment; a template change that was never deployed needs a release. The job resolves the serving revision and the dev CIDRs exactly like the deploy, so a clean environment reports zero changes.

### RB-15 Certificate expiring (Front Door)
Managed certificates on the default `*.azurefd.net` hosts renew automatically. A custom domain with a customer certificate in Key Vault: rotate the secret version and update the Front Door custom domain (not templated yet, backlog FD). Check `FrontDoorHealthProbeLog` after the change.

### RB-16 Rotating the dev identity provider key (local only)
`docker compose down && docker volume rm ade-pipeline_devidpkeys && make up`. Everyone signs in again.

## Backup and recovery

| Store | Mechanism | Local equivalent |
|---|---|---|
| Azure SQL | Automated backups with point-in-time restore, long-term retention configured in Bicep | Docker volume `sqldata`; `make reset` destroys it |
| Documents (ADLS Gen2) | Soft delete, container-level immutability policy; geo-redundant storage (blob versioning is off — unavailable on the hierarchical-namespace account, which is why container immutability is used; see ADR-003) | Azurite volume `azuritedata` |
| Staging | Transient; lifecycle deletes after 7 days | same |
| Audit ledger | Append-only; digests can be stored externally (not configured in this build) | same table type in SQL Server 2022 |

Restore drill: procedure in RB-08 and `architecture/PRODUCTION_READINESS.md` section 5. Rehearsed locally on 11 October 2026 (backup, restore to a side database, ledger verification, RLS on the copy; `docs/RELEASE_READINESS.md` §2). Azure point-in-time restore itself still needs an Azure environment (backlog RESTORE).

## Alerts to configure (Azure Monitor)

Four of these are deployed by `infra/bicep/modules/monitoring.bicep` as scheduled query rules on
the API's JSON logs once `alertEmails` is set in the parameter file (API 5xx rate, job failures,
dead-lettered notifications, purge blocked by a legal hold); thresholds are first guesses to tune
in the test environment. Logs carry `duration_ms`, `revision`, `sitio_id`/`lote_id`/`archivo_id`
/`subida_id` from the route, and `job_name`/`job_run` on job lines. An administrator can call
`GET /healthz/deps` for dependency reachability with latency.

Readiness probe failures, HTTP 5xx rate above 5 % over 10 minutes (the Bicep alert rule and `architecture/PRODUCTION_READINESS.md` §2.5), `promote` sessions waiting over `SCAN_WAIT_SECONDS`, outbox `fallida` count increasing, purge job failures, SQL DTU/vCore above 80 %, and any `unhandled_error` log event. Exact thresholds and routing are in `architecture/PRODUCTION_READINESS.md`.
