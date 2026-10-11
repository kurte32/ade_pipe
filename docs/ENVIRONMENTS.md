# Environments and configuration

Three environments share one codebase. Business logic never branches on the environment; only
adapters selected by configuration differ.

| | Local development | Automated testing (CI) | Production (Azure) |
|---|---|---|---|
| Where | Developer machine, docker compose | GitHub Actions runner | Azure Container Apps |
| Config source | `.env` (copied from `.env.example`) | `.env.example` values exported to the job | Bicep parameters, Container App env, Key Vault references |
| Database | SQL Server 2022 container, SQL auth with `pipeline_app` | SQL Server 2022 container | Azure SQL Database, Entra-only auth, managed identity |
| Storage | Azurite (both containers in one emulated account) | Azurite | Two storage accounts (flat staging, ADLS Gen2 documents) |
| Identity | `tools/dev-idp` local OIDC issuer | `tools/dev-idp` | Microsoft Entra ID |
| Malware scan | `SCAN_MODE=none` | `SCAN_MODE=none` | `SCAN_MODE=defender` |
| Notifications | `NOTIFY_MODE=log` | `NOTIFY_MODE=log` | `NOTIFY_MODE=graph` (Teams activity feed) |
| Directory | `DIRECTORY_MODE=dev` | `DIRECTORY_MODE=dev` | `DIRECTORY_MODE=graph` |
| Telemetry | stdout JSON | stdout JSON | stdout JSON + Application Insights |
| Jobs | `scheduler` compose service loop | run on demand in tests | Container Apps Jobs (cron) |

`ENVIRONMENT` has three values and the guard in `backend/app/core/config.py` keys on them:

| Value | Where | What it means |
|---|---|---|
| `local` | compose stack, CI | The only value that may trust the SQL Server certificate, serve `/api/docs`, accept the dev identity provider and run `e2e-cleanup` |
| `test` | Azure dev and test (UAT) | *Deployed*: Entra auth with the issuer and JWKS pinned to `login.microsoftonline.com`, managed identity to SQL, Azure storage, a real tenant id, `AUTH_ADMIN_AZP` set, `TEAMS_APP_ID` set when notifications use Graph. Substitute scan, notification and directory modes are allowed |
| `production` | Azure prod | Everything `test` requires, plus Defender scanning and Graph notifications and directory |

The container image defaults to `ENVIRONMENT=production`, so a container started without the
variable fails closed. Deployed non-production never trusts an unvalidated certificate (audit IDN-2).

## Environment variables

| Variable | Local (`.env`) | CI | Azure (source) |
|---|---|---|---|
| `ENVIRONMENT` | `local` | `local` | `production` (param `environmentName`; dev and test use `test`, see above) |
| `LOG_LEVEL` | `INFO` | `INFO` | param `logLevel` |
| `APP_PUBLIC_URL` | `http://localhost:5173` | same | param `appPublicUrl` (Front Door host) |
| `DB_HOST` | `localhost` (compose sets `sqlserver` for containers) | `localhost` | SQL server FQDN (module output) |
| `DB_PORT` | `1433` | `1433` | `1433` |
| `DB_NAME` | `pipeline` | `pipeline` | `pipeline` |
| `DB_AUTH` | `sql` | `sql` | `entra` |
| `DB_USER` | `pipeline_app` | `pipeline_app` | API managed identity name |
| `DB_PASSWORD` | dev value | dev value | not set (token auth) |
| `DB_ADMIN_USER`, `DB_ADMIN_PASSWORD` | `sa` + dev value (db-init, migrations) | same | not set; the migration job uses the migration identity |
| `AUTH_MODE` | `dev` | `dev` | `entra` |
| `AUTH_TENANT_ID` | dev GUID | dev GUID | param `authTenantId` |
| `AUTH_AUDIENCE` | dev GUID | dev GUID | param `authAudience` (pipeline-api client id) |
| `AUTH_ALLOWED_AZP` | two dev GUIDs | same | param `authAllowedAzp` |
| `AUTH_ADMIN_AZP` | admin dev GUID | same | param `authAdminAzp`: Admin is honoured only from this client id, and that client never acts as Coordinador (required when deployed) |
| `FRONT_DOOR_ID` | empty | empty | output of the Front Door profile; `/api/*` requests must carry a matching `X-Azure-FDID` (required in production, backlog A3) |
| `RATE_LIMIT_*_PER_MINUTE` | defaults (300 captures, 300 transitions, 120 uploads, 1200 parts, 30 loads) | same | same; per user, per replica; 0 disables one |
| `CORS_ALLOWED_ORIGINS` | empty | empty | empty behind Front Door; the two SWA hostnames when `deployFrontDoor=false` (dev), computed in `main.bicep` |
| `AUTH_ISSUER` | `http://localhost:8001/<tenant>/v2.0` | same | `https://login.microsoftonline.com/<tenant>/v2.0` (computed) |
| `AUTH_JWKS_URL` | dev-idp JWKS (compose overrides host) | `http://localhost:8001/...` | Entra discovery keys URL (computed) |
| `DEV_IDP_URL` | `http://localhost:8001` | same | not set |
| `STORAGE_MODE` | `azurite` | `azurite` | `azure` |
| `STORAGE_BLOB_ENDPOINT`, `STORAGE_ACCOUNT_NAME`, `STORAGE_ACCOUNT_KEY` | Azurite well-known values | same | not set |
| `STORAGE_STAGING_ACCOUNT_URL`, `STORAGE_DOCUMENTS_ACCOUNT_URL` | empty | empty | module outputs (blob endpoints) |
| `STORAGE_STAGING_CONTAINER`, `STORAGE_DOCUMENTS_CONTAINER` | `staging`, `documents` | same | same |
| `SCAN_MODE` | `none` | `none` | `defender` |
| `NOTIFY_MODE` | `log` | `log` | param `notifyMode`: `log` in dev and test until the Teams app exists (backlog TEAMS), `graph` in prod (required by the guard) |
| `DIRECTORY_MODE` | `dev` | `dev` | `graph` |
| `GRAPH_BASE_URL` | Graph v1.0 | same | param `graphBaseUrl` |
| `TEAMS_APP_ID` | empty | empty | param `teamsAppId` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | empty | empty | Key Vault reference `appinsights-connection-string` |
| `AZURE_CLIENT_ID` | not set | not set | user-assigned identity client id (selects the identity for `DefaultAzureCredential`) |
| Limits (`PDF_MAX_BYTES`, `PDF_MAX_PAGES`, `UPLOAD_CHUNK_BYTES`, `PHOTO_MAX_BYTES`, `LOAD_MAX_ROWS`, `LOAD_MAX_BYTES`, `DUPLICATE_DISTANCE_METERS`, `SUSPICIOUS_NAME_WORDS`) | `.env.example` defaults | same | config.py defaults (add to `commonEnv` in `containerapps.bicep` to override) |
| `RETENTION_YEARS` | default 5 | 5 | param `retentionYears` |
| `MAX_REQUEST_BYTES` | 12582912 | 12582912 | settings default (12 MiB) |
| `TRUSTED_PROXY_HOPS` | 0 (socket peer) | 0 | 2 with Front Door, 1 without (derived from param `deployFrontDoor`) |

Frontend configuration: locally, `.env.development` in each app sets `VITE_AUTH_MODE=dev` and the dev
ids. CI builds one environment-neutral bundle with only `VITE_AUTH_MODE=msal`; each deployment writes
`config.json` next to the bundle with that environment's `VITE_TENANT_ID`, `VITE_SPA_CLIENT_ID` and
`VITE_API_CLIENT_ID` (from GitHub environment variables), read by the app at startup. The auth mode
cannot be changed through `config.json`.

## Local substitutes and their limits

| Azure service | Local substitute | Behavior verified locally | Differences and limitations |
|---|---|---|---|
| Azure SQL Database | SQL Server 2022 Developer (container) | RLS with `SESSION_CONTEXT`, `rowversion`, append-only ledger tables, same T-SQL | SQL authentication instead of Entra tokens; no automatic ledger digest storage; no PITR/LTR; `sa` exists (never used by the API after `db-init`) |
| Azure Blob Storage (staging, flat) | Azurite blob service | Block staging, block list, commit, blob index tags, server-side copy, range reads | No Defender scanning; tags are set by the application in `SCAN_MODE=none`; no lifecycle rules (abandoned sessions are expired by the `expire_uploads` job instead) |
| ADLS Gen2 (documents) | Same Azurite account, container `documents` | Blob API reads and writes; path layout `pipeline/{sitio}/{tipo}/...` | No hierarchical namespace, no immutability or legal hold, no soft delete by default, no OneLake shortcut; the Blob API is the only API used so code paths are identical |
| Microsoft Entra ID | `tools/dev-idp` (local OIDC issuer) | RS256 tokens with Entra v2 claim shape, JWKS discovery, same validation code | No MFA, Conditional Access, refresh tokens or Intune; tokens are minted for any listed dev user; keys live in a docker volume |
| Defender for Storage | `SCAN_MODE=none` | Promotion path, tag read, rejection path exercised with tags written by tests | No real malware detection; production refuses this mode |
| Microsoft Teams via Graph | `NOTIFY_MODE=log` | Outbox table, retry, backoff and status transitions | Delivery is a structured log line, not a Teams message |
| Microsoft Graph directory | `DIRECTORY_MODE=dev` (dev-idp `/users`) | Email to oid resolution through the same interface | No real tenant lookup; unknown emails fail the same way |
| Managed identity | SQL login and Azurite account key | n/a | `DefaultAzureCredential` is only exercised in Azure |
| Application Insights | disabled | stdout JSON logs with correlation ids | No traces or metrics export locally |
| Container Apps Jobs | `scheduler` compose service | Same job entrypoints (`python -m app.jobs.run <name>`) | Interval loop instead of cron; one process for all jobs |
| Front Door + WAF | Vite dev server proxy (`/api`, `/dev-idp`) | Same-origin routing as production | No WAF, no TLS, no rate limiting locally |
