# Delivery report · Pipeline de Posibles Tiendas

Date: 2026-10-10. Branch: `implementation` (merged to `main` as PR #1 on 2026-10-11; later work
is on `prod-readiness` and `ux-redesign`, see `../CHANGELOG.md`). Everything below was executed on the
development machine described in `IMPLEMENTATION_STATUS.md`. No Azure resources were created,
modified or destroyed.

Verification vocabulary, applied per item throughout:

- **Implemented and locally verified**: an automated test executed against the local stack passed.
- **Statically validated**: lint, type-check, build or template validation only; never executed.
- **Validated in a test Azure environment**: none in this build.
- **Deployed and verified in Azure**: none in this build.
- **Not verified**: written but no evidence.

## 1. Implemented functionality

- **Identity.** One token validation path (issuer, audience, tenant, delegated scope, authorized client, roles) used for Entra ID and for a local OIDC issuer (`tools/dev-idp`) that mints real RS256 tokens. The API refuses to start in production with any development mode enabled. Two frontend auth providers: MSAL (localStorage cache, redirect flow) and the dev picker.
- **Coordinator PWA** (`apps/pwa-coordinador`): my sites list with search and filters, site detail, contact and measurement capture, photo capture with client-side compression, resumable chunked PDF upload per document type, one-step status advance with client precheck, proposal to discard, history, in-app notifications, conflict panel. Offline-first: Dexie cache, per-site FIFO queue with chained ETags and idempotency keys, foreground sync on start, reconnect, timer and enqueue, delta sync with removals. Installable PWA with a Workbox service worker that never caches the API or the auth redirect.
- **Admin web** (`apps/web-admin`): dashboard by status, sites table and detail with return (reason catalog, comment, If-Match), discard and reassign dialogs, bulk load (CSV, XLSX, XLS) with preview, per-row and bulk decisions, single-transaction confirm and cancel, equivalence table with directory resolution, audit log viewer with filters and pagination, document download.
- **API** (`backend/app`, FastAPI modular monolith): identity, sitios (list, detail with ETag, delta), transiciones (rules in code, parameters in catalogs), notificaciones (outbox, in-app, Teams activity feed or log), auditoria (append-only writer and admin viewer), cargas (parser with signature checks, 18 distinct validation rule codes, staging, reload semantics), equivalencias (dev and Graph directories), archivos (upload sessions, block upload to staging, hash and type and PDF checks, scan step, promotion, Range downloads, soft delete). Problem Details errors, correlation ids, structured JSON logs with redaction, health and readiness endpoints.
- **Database**: Azure SQL compatible schema on SQL Server 2022 locally. Row-Level Security with filter and block predicates on seven tables driven by `SESSION_CONTEXT`, Admin and Sistema bypass by role, least-privilege application role (no DDL, no policy changes, INSERT-only on ledger tables), append-only ledger tables for audit and status history, catalogs seeded by migration.
- **Jobs**: promote, outbox, expire_uploads, purge, idempotency_cleanup as CLI entrypoints from the same image; local scheduler container; Container Apps Jobs in Bicep.
- **Infrastructure**: 13 Bicep modules and 3 parameter files for the approved topology (VNet, private endpoints, Container Apps with jobs, Azure SQL Entra-only, two storage accounts with Defender scanning and immutability, Key Vault, ACR, Static Web Apps, Front Door Premium with WAF, monitoring, identities). GitHub Actions: CI with integration tests against SQL Server, Azurite and the dev issuer; build, scan and deploy by digest with OIDC; nightly drift check.
- **Local stack**: `docker compose` with SQL Server 2022, Azurite, dev issuer, API with hot reload and migrations, scheduler. `make` targets for every routine task. Synthetic 87-row sample file matching TDD Anexo A.

## 2. Requirement-by-requirement status

See `IMPLEMENTATION_STATUS.md` for the full table with evidence per RF, RNF and HU. Summary:

| Group | Implemented and locally verified | Implemented, part not verifiable locally | Not verified |
|---|---|---|---|
| RF-01 to RF-11 | RF-02, 03, 04, 05, 06, 09, 10 | RF-01 (MSAL), RF-07 (Teams delivery), RF-08 (Defender scan), RF-11 (immutability) | none |
| RNF-01 to RNF-08 | RNF-02, 05, 06, 07 | RNF-01 (encryption and private network only in Bicep), RNF-04 | RNF-03 (device), RNF-08 (4G timing) |
| HU-01 to HU-18 | HU-02 to HU-13, HU-15 | HU-01 (MSAL), HU-14 (Teams), HU-16 (Fabric), HU-17 (immutability) | HU-18 (pen test) |

## 3. Architectural changes and justification

| Change | Why | Where recorded |
|---|---|---|
| Local OIDC issuer (`tools/dev-idp`) instead of a mocked auth layer | Keeps one validation code path; tokens are real RS256 JWTs; production guard forbids it | `ENVIRONMENTS.md`, `config.py` |
| Container-level time-based immutability instead of version-level | Blob versioning is unavailable on hierarchical-namespace accounts | ADR-003 addendum |
| Multiple-revision mode kept (the infra fork had used Single) | Approved rollback is a traffic shift | ADR-010, `OPERATIONS.md` RB-09, `deploy-environment.yml` |
| Delta watermark `MIN_ACTIVE_ROWVERSION() - 1` instead of `@@DBTS` | In-flight transactions would otherwise be skipped by the next delta | `sitios/service.py` |
| `Sistema` role for background jobs in the RLS predicate and audit | Jobs need to see all rows and must leave an audit trail distinct from users | baseline migration, `security.py` |
| Coordinator can only propose a discard (`en_revision_admin`), admin confirms | Terminal states are a business decision (TO_BE open question 5) | `transiciones/service.py` |
| Admin app builds with a configurable base path (`/admin/`) | Front Door routes `/admin/*` to the admin Static Web App | `apps/web-admin/vite.config.ts` |
| Plain ARM resources instead of Azure Verified Modules | Avoids registry resolution in offline validation; no functional difference | `infra/bicep/modules` |
| Provisional values for TDD pendientes 4, 5, 7, 8 | Needed to run end to end; all are configuration or catalog rows | migration catalogs, `.env.example` |

## 4. Running locally

Full guide: `LOCAL_DEVELOPMENT.md`. Verified from clean volumes on 2026-10-10 (audit finding D-01:
`.env.example` was untracked, so a real `git clone` could not run the first line until the fix; see
`docs/audit/`):

```bash
cp .env.example .env
make up            # 42 s from empty volumes to healthy API with migrations applied
make db-seed       # 10 equivalences, 87 sites through the real bulk-load path
pnpm install --frozen-lockfile
pnpm dev           # PWA http://localhost:5173, admin http://localhost:5174
```

## 5. Automated tests executed

| Command | Result |
|---|---|
| `make test` (pytest in the API container, unit + integration against SQL Server, Azurite, dev issuer) | 125 passed |
| `make test-unit` | 72 passed |
| `pnpm test` (vitest: auth 4, api-client 3, web-admin 7, pwa-coordinador 6) | 20 passed |
| `make e2e` (Playwright, 3 projects) | 14 passed |
| `make lint` (ruff check, ruff format, mypy strict on 61 files, eslint, tsc on 6 packages) | clean |
| `pnpm build` (both apps, PWA service worker generated) | success |
| `bash infra/bicep/validate.sh` | 13 modules, 3 parameter files pass build and lint |
| `pip-audit` on the locked backend dependencies | no known vulnerabilities |
| `pnpm audit --audit-level high` (matching ci.yml) after upgrading vitest to 4.1.11 | no known vulnerabilities |
| actionlint and YAML parse of 4 workflows | clean (run by the infra fork; never executed on GitHub) |

What the backend integration tests cover: token negatives (expired, wrong audience, issuer, tenant, missing or wrong scope, unknown client, missing or malformed oid, bad signature), 401/403 paths, cross-coordinator isolation at API and at database level on a reused pooled connection, block predicate on cross-owner insert, app role denied on ledger tables and security policy, contact and visit upsert with idempotent replay, transition chain with threaded ETags, 428, 412 with current state, 422 with missing requirements, admin return with history, outbox and in-app notice, outbox retry and failure path, reassignment, audit viewer, bulk load of the 87-row file with rule counts, decisions, confirm, reload semantics, invalid files, resumable 3-part upload with lost and re-sent parts, hash mismatch, encrypted and over-limit PDFs, type spoofing, Range downloads, versioning of documents, soft delete, session expiry, purge.

## 6. Browser end-to-end results

The Claude in Chrome extension was not connected during the build. It became available at the end of the session and a short manual pass was done in real Chrome: PWA sign-in with the dev picker, the site list (10 sites for `ard`, devuelto badges visible), the site detail (status section listing the four missing documents, contact and measurements forms); admin sign-in, dashboard counts (89 Sitio Prospectado, 1 Dueño Localizado, 1 Primera visita, 2 recent loads), and the Sitios table (`GET /api/v1/sitios?limit=50` returned 200). No console errors on either app. That pass is evidence of rendering and navigation only; the workflow evidence is the Playwright suite below, performed with Playwright 1.64.0 on headless Chromium using Pixel 7 emulation for the PWA and Desktop Chrome for the admin. Console errors were asserted empty (favicon and deliberate 4xx validation responses excluded). All 14 scenarios passed, on the running stack and again after a full `make reset`:

| Project | Scenario | Result |
|---|---|---|
| pwa-mobile | Sign in as coordinator, site list rendered | pass |
| pwa-mobile | User without role is refused with a clear message | pass |
| pwa-mobile | Session survives reload | pass |
| pwa-mobile | Capture contact, advance to Dueño Localizado, capture visit, advance to Primera visita, history updated | pass |
| pwa-mobile | Offline: capture and advance while `setOffline(true)`, pending badge, reconnect, sync, new status | pass |
| pwa-mobile | Admin returns the site via API while open; PWA shows devuelto and conflict panel; discard local change | pass |
| pwa-mobile | Photo captured, compressed, uploaded and published after sync | pass |
| pwa-mobile | PDF uploaded in chunks for a document type, listed and downloadable (`%PDF`) | pass |
| admin-desktop | CSV load with one error and warnings, approve, confirm, new site searchable | pass |
| admin-desktop | Invalid file rejected with Problem Details | pass |
| admin-desktop | Return with reason and comment, history row, reassign to another coordinator | pass |
| admin-desktop | Stale ETag yields a clear conflict message | pass |
| admin-desktop | Equivalences: unknown email rejected per code, nothing saved, valid email saved | pass |
| admin-desktop | Audit viewer filter by action with expandable detail | pass |

Not covered by browser tests: MSAL sign-in (no tenant), installed PWA behavior on Android (no device), 150 MB uploads (test files are small).

## 7. Security and reliability validation

> **Audit correction (2026-10-10):** an independent audit found that optimistic concurrency was
> **not** enforced at the database — the ETag/rowversion check ran in Python, so concurrent writes
> with the same ETag all committed (finding B-01, Critical). This is now **fixed and verified**: the
> rowversion is enforced in the UPDATE (SQLAlchemy `version_id_col`), a concurrent same-ETag burst
> returns one success and the rest 412, and a regression test guards it. The idempotency claim is
> still qualified (B-02: concurrent replays return 500, not the stored response — open). See
> `docs/audit/`.

Validated locally with automated tests: token validation negatives, role enforcement, three-layer isolation including pooled connections and raw SQL, block predicates, least-privilege grants, append-only ledger behavior, file type by signature, PDF structure and limits, hash verification, idempotent replay, optimistic concurrency, outbox retry and dead-letter, upload session expiry, purge with retained metadata, audit on every write and download, Problem Details without stack traces, log redaction of personal data keys, production configuration guard.

Implemented but validated only statically or not at all: TLS and private endpoints (Bicep), Front Door WAF rules (Bicep), Defender for Storage scanning (code path and Bicep), immutability and legal hold (Bicep), managed identity to SQL via access token (code path), Key Vault references (Bicep), OIDC federation for deployments (workflow), MSAL token lifetimes and Conditional Access (not testable locally), rate limiting (delegated to WAF by design), backup and restore drill (needs Azure), penetration test (needs a deployed environment).

## 8. Azure deployment readiness and blockers

Ready: Bicep for dev, test and prod (statically validated), workflows (statically validated), container image (built locally, runs as non-root), application production guard, configuration contract documented in `ENVIRONMENTS.md` and `AZURE_DEPLOYMENT.md`.

Blockers before a first deployment, all external to this repository:

1. Entra app registrations per environment (guide Part A plus ADR-006 additions), groups, Assignment Required, Conditional Access policies.
2. Azure subscription with OIDC federation for GitHub, resource group, Entra admin group for SQL.
3. Graph application permissions `User.ReadBasic.All` and `TeamsActivity.Send` on the API managed identity and a published Teams app id.
4. Fabric workspace identity and trusted workspace access for the OneLake shortcut; VNet data gateway for Mirroring behind the private endpoint.
5. Defender for Storage plan enabled on the subscription.
6. Decisions on TDD pendientes 4, 5, 7, 8 (document catalog, minimum fields, retention start, return reasons) to replace the provisional values.

Then: `test` environment deployment, Phase 0 spikes from `architecture/IMPLEMENTATION_PLAN.md`, restore drill, penetration test.

## 9. Known defects, limitations, residual risks

- `pip-audit` and `pnpm audit` have been run locally once; CI has never run on GitHub, so the workflows themselves are unproven.
- The Teams notifier, Graph directory, MSAL provider, Entra SQL token injection, Defender tag reading and cross-account copy with managed identity are written and type-checked but have never executed against real services.
- SHA-256 of a PDF is computed in browser memory; fine up to the 150 MB limit on a desktop, not measured on a phone.
- The purge job treats any delete failure as "protected, skip"; in Azure this is the intended behavior for immutability, but it also hides misconfiguration until the log is read.
- Container-level immutability makes superseded document versions undeletable for five years (see ADR-003 addendum). Policy locking is manual and irreversible.
- Playwright admin tests create "E2E" named sites and one load batch per run and are not cleaned up; backend tests clean up after themselves.
- Chrome extension validation did not happen; Playwright emulation is the evidence.
- The `.xls` fixture used by cargas tests was produced with LibreOffice from the synthetic xlsx; real legacy files may differ.
- `scheduler` runs every job on a fixed interval locally; Azure uses per-job schedules, so timing differs between environments.

## 10. Prioritized remaining work

1. Create the Entra registrations and run the MSAL sign-in and token negative cases against the real tenant (RF-01, HU-01). Then the Phase 0 device spike (Edge, Intune, 24 h offline).
2. Deploy `test` with Bicep, run the CI workflow on GitHub, execute the restore drill and the integration suite against Azure SQL and real storage; verify Defender tags, immutability, shortcut and Mirroring (Phase 0 spikes B and C).
3. Replace provisional catalogs and limits with the business answers to TDD pendientes 4, 5, 7, 8 (migration with catalog updates; no code change expected).
4. Publish the Teams app and verify activity-feed delivery; otherwise switch `NOTIFY_MODE` to a Power Automate webhook (ADR-007 fallback).
5. Penetration test and RLS test report (HU-18); Defender for Cloud recommendations review.
6. Observability wiring in Azure: Application Insights connection string, dashboards and alerts from `architecture/PRODUCTION_READINESS.md`.
7. Nice to have: streaming SHA-256 in the PWA, cleanup fixtures for admin Playwright tests, pin GitHub Actions to commit SHAs.
