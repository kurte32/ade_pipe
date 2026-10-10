# Implementation status

Updated: 2026-10-10 (final for this build). Verification vocabulary used below: `implemented and locally verified` (automated test executed against the local stack), `statically validated` (lint, build or template validation only), `validated in a test Azure environment` (none in this build), `deployed and verified in Azure` (none in this build), `not verified`. Original statuses: `not started` · `in progress` · `implemented` · `tested locally` (automated test executed and passing) · `statically validated` (lint/build only, no runtime) · `unverified` (needs Azure or a device) · `blocked` (external dependency).

## Baseline findings (Phase One)

- Repository before this build: two PDFs, one review, `architecture/`. No code, tests, CI, or infrastructure.
- Development machine: Ubuntu (kernel 6.8), 16 CPU, 62 GB RAM, 23 GB free disk. Docker 29 + Compose 2.27, Node 22.23 + pnpm 12 (corepack), Python 3.12 + uv, make, gh. No ODBC driver on the host, no Azure CLI. Standalone Bicep CLI installed under `~/.local/bin`.
- Local substitutes verified by probe on 2026-10-10: SQL Server 2022 (CU27) supports `SESSION_CONTEXT` and append-only ledger tables (UPDATE rejected with error 37359). Azurite supports block staging, block list, blob index tags, server-side copy, and range reads.
- Chrome extension (Claude in Chrome) is **not connected** in this session. Browser workflow validation uses Playwright with headless Chromium; this is recorded as such and is not claimed as Chrome extension validation.
- The TDD's sample file `pipeline_nacional_mx_20261009.xlsx` is not available. A synthetic file matching Anexo A is generated into `samples/`.

## Requirements

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| RF-01 | Coordinator signs in with corporate Entra account from mobile | implemented and locally verified (dev issuer); MSAL path not verified | Token validation: 11 unit negatives + integration; Playwright sign-in on Pixel 7 emulation (`pwa.signin.spec.ts`). `MsalAuthProvider` written and type-checked only; no tenant available |
| RF-02 | Coordinator lists and views only assigned sites | implemented and locally verified | API, service and DB (pooled connections) isolation tests; PWA list and detail in `pwa.flow.spec.ts` |
| RF-03 | One-step status advance with minimum requirements | implemented and locally verified | Rules unit tests; 13 integration tests (428/412/422, idempotent replay); PWA two-step advance flow |
| RF-04 | Capture contact, measurements with photos, required documents | implemented and locally verified | Contact and visit forms, photo capture with compression, PDF per document type (`pwa.flow.spec.ts` photo and PDF scenarios) |
| RF-05 | Admin bulk load CSV/XLSX/XLS with preview, warnings, approval | tested locally | Backend (parser, 38 rule tests, confirm, reload) and admin UI (Playwright `admin.cargas.spec.ts`: CSV with error and warnings, approve, confirm, new site searchable; invalid file 422) |
| RF-06 | Admin returns a site to an earlier status with mandatory reason | tested locally | Backend tests plus Playwright `admin.sitios.spec.ts` (devolver with motivo and comentario, historial row, stale ETag conflict message) |
| RF-07 | Teams notification on return | implemented; delivery not verified | Outbox, retry and in-app notice tested locally in log mode; Graph activity-feed notifier needs a tenant, Teams app and `TeamsActivity.Send` |
| RF-08 | Chunked resumable PDF upload, validation, storage | implemented and locally verified; scan not verified | Backend: 3-part resumable upload, sha256, signature, pages, encrypted, Range download; PWA resumable uploader in `pwa.flow.spec.ts`. Defender scanning only in `SCAN_MODE=defender` (Azure) |
| RF-09 | Admin manages user→email equivalences and reassignment | tested locally | Playwright `admin.equivalencias.spec.ts` (unknown email rejected per code, valid saved) and reasignar flow; Graph directory unverified |
| RF-10 | Immutable audit log | tested locally | Ledger tables, INSERT-only grants, audit on every write and download, admin viewer endpoint tested |
| RF-11 | 5-year retention and audited purge | implemented and locally verified; immutability statically validated | Purge job tests; Bicep container-level immutability policy (see ADR-003 addendum); start event is TDD pendiente 7 |
| RNF-01 | Isolation at API, service, DB; encryption; no secrets in code | implemented and locally verified (local); encryption and private networking statically validated | RLS on 7 tables with filter and block predicates; app role without DDL or policy rights; no secrets in repo (dev-only values in `.env.example`); TLS and private endpoints in Bicep only |
| RNF-02 | Offline capture, idempotent operations | implemented and locally verified | Sync engine unit tests (6) and offline Playwright scenario (`context.setOffline`); Idempotency-Key replay store |
| RNF-03 | Intune-managed Android, PWA-capable browser | not verified | Needs a managed device; PWA manifest and service worker build verified |
| RNF-04 | 5-year retention | see RF-11 | |
| RNF-05 | PDF ≤ 50 pages, ≤ 150 MB | tested locally | Validation tests (51 pages rejected, size limit, encrypted) |
| RNF-06 | Store UTC, show Mexico City | implemented and locally verified | UTC storage tests; `formatMexicoCity` used in both apps; admin date filter conversion unit test |
| RNF-07 | Audit every write and download | tested locally | Download audit committed before streaming |
| RNF-08 | Initial list < 3 s on 4G | not verified | Needs a device on 4G; list is a single paged query |

## User stories

| HU | Story | Status | Evidence |
|---|---|---|---|
| HU-01 | Sign in with corporate account | implemented and locally verified (dev issuer); MSAL not verified | `pwa.signin.spec.ts`, admin sign-in in every admin spec |
| HU-02 | See only my sites | implemented and locally verified | RLS tests, `pwa.flow.spec.ts` |
| HU-03 | Load CSV/XLSX/XLS and preview | tested locally | Playwright `admin.cargas.spec.ts` |
| HU-04 | Approve or exclude doubtful rows | tested locally | Playwright `admin.cargas.spec.ts` |
| HU-05 | Manage equivalences | tested locally | Playwright `admin.equivalencias.spec.ts` |
| HU-06 | Site detail | implemented and locally verified | `pwa.flow.spec.ts` |
| HU-07 | Capture contact, advance to Dueño Localizado | implemented and locally verified | `pwa.flow.spec.ts` online flow |
| HU-08 | Capture measurements, advance to Primera visita | implemented and locally verified | `pwa.flow.spec.ts` online flow |
| HU-09 | Upload PDFs, advance to Recepción de documentos | implemented and locally verified | PDF upload scenario; transition rule requires all 4 provisional document types (catalog is TDD pendiente 4) |
| HU-10 | Work offline, auto sync | implemented and locally verified | Offline scenario in `pwa.flow.spec.ts`; engine unit tests |
| HU-11 | Resume interrupted upload | implemented and locally verified | Backend resume tests; PWA uploader persists the session id and resumes from `GET /subidas/{id}` |
| HU-12 | Upload photos | implemented and locally verified | Photo scenario in `pwa.flow.spec.ts` |
| HU-13 | Admin return with reason | tested locally | Playwright `admin.sitios.spec.ts` |
| HU-14 | Teams notice on return | implemented; Teams delivery not verified | In-app notice and conflict panel verified in `pwa.flow.spec.ts` (admin devolución scenario) |
| HU-15 | Audit log viewer | tested locally | Playwright `admin.auditoria.spec.ts` (filter by action, detail JSON) |
| HU-16 | Documents in Fabric with metadata | implemented; Fabric exposure statically validated | Metadata rows and `documents` container path verified locally; OneLake shortcut and Mirroring exist only in Bicep and docs |
| HU-17 | Purge after 5 years | implemented and locally verified; immutability not verified | Purge job tests |
| HU-18 | Pen test and RLS tests before production | partially: RLS tests automated; pen test not done | RLS suite in CI definition; penetration test requires a deployed environment |

## Infrastructure and operations

| Item | Status | Evidence |
|---|---|---|
| Local stack (compose: SQL Server, Azurite, dev IdP, API, scheduler) | implemented | `make up`; health and readiness verified |
| Alembic baseline with RLS, ledger, app user | tested locally | `backend/migrations/versions/1130828e690d_baseline.py`; downgrade and upgrade cycle verified |
| Bicep templates per `AZURE_DESIGN.md` | statically validated | 13 modules + 3 param files, `bash infra/bicep/validate.sh` passes; nothing deployed |
| GitHub Actions CI/CD | statically validated | ci, build-deploy, deploy-environment, drift; actionlint clean; never executed on GitHub |
| Observability (structured logs, correlation, App Insights) | implemented | JSON logs, correlation id header, forbidden-field redaction; App Insights wiring unverified locally |
| Local development guide verified from clean clone | verified | `make reset && make up` (42 s) `&& make db-seed`, `pnpm install --frozen-lockfile`, `pnpm build`, `pnpm dev`, `make e2e` (14 passed), `make test` (125 passed) on 2026-10-10 |
