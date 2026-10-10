# Implementation status

Updated: 2026-10-10 (wave 1: backend modules, infra). Statuses: `not started` · `in progress` · `implemented` · `tested locally` (automated test executed and passing) · `statically validated` (lint/build only, no runtime) · `unverified` (needs Azure or a device) · `blocked` (external dependency).

## Baseline findings (Phase One)

- Repository before this build: two PDFs, one review, `architecture/`. No code, tests, CI, or infrastructure.
- Development machine: Ubuntu (kernel 6.8), 16 CPU, 62 GB RAM, 23 GB free disk. Docker 29 + Compose 2.27, Node 22.23 + pnpm 12 (corepack), Python 3.12 + uv, make, gh. No ODBC driver on the host, no Azure CLI. Standalone Bicep CLI installed under `~/.local/bin`.
- Local substitutes verified by probe on 2026-10-10: SQL Server 2022 (CU27) supports `SESSION_CONTEXT` and append-only ledger tables (UPDATE rejected with error 37359). Azurite supports block staging, block list, blob index tags, server-side copy, and range reads.
- Chrome extension (Claude in Chrome) is **not connected** in this session. Browser workflow validation uses Playwright with headless Chromium; this is recorded as such and is not claimed as Chrome extension validation.
- The TDD's sample file `pipeline_nacional_mx_20261009.xlsx` is not available. A synthetic file matching Anexo A is generated into `samples/`.

## Requirements

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| RF-01 | Coordinator signs in with corporate Entra account from mobile | in progress | Backend token validation tested locally (unit negatives + dev issuer). MSAL frontend pending; Entra tenant unverified |
| RF-02 | Coordinator lists and views only assigned sites | in progress | API and DB isolation tested locally (`tests/integration/test_identity_and_rls.py`, pooled connections). PWA pending |
| RF-03 | One-step status advance with minimum requirements | in progress | Backend tested locally (rules in code, If-Match 412/428, idempotent replay); PWA pending |
| RF-04 | Capture contact, measurements with photos, required documents | in progress | Backend endpoints tested locally; PWA pending |
| RF-05 | Admin bulk load CSV/XLSX/XLS with preview, warnings, approval | tested locally | Backend (parser, 38 rule tests, confirm, reload) and admin UI (Playwright `admin.cargas.spec.ts`: CSV with error and warnings, approve, confirm, new site searchable; invalid file 422) |
| RF-06 | Admin returns a site to an earlier status with mandatory reason | tested locally | Backend tests plus Playwright `admin.sitios.spec.ts` (devolver with motivo and comentario, historial row, stale ETag conflict message) |
| RF-07 | Teams notification on return | in progress | Outbox and job tested locally in log mode; Graph activity-feed delivery implemented, unverified (needs tenant) |
| RF-08 | Chunked resumable PDF upload, validation, storage | in progress | Backend tested locally (3-part resumable upload, sha256, signature, pages, encrypted PDF, Range download); PWA uploader pending; Defender scan unverified |
| RF-09 | Admin manages user→email equivalences and reassignment | tested locally | Playwright `admin.equivalencias.spec.ts` (unknown email rejected per code, valid saved) and reasignar flow; Graph directory unverified |
| RF-10 | Immutable audit log | tested locally | Ledger tables, INSERT-only grants, audit on every write and download, admin viewer endpoint tested |
| RF-11 | 5-year retention and audited purge | in progress | Purge job tested locally (metadata kept, 410 on download, audit as Sistema); Azure immutability policy statically validated only; start event is TDD pendiente 7 |
| RNF-01 | Isolation at API, service, DB; encryption; no secrets in code | in progress | RLS filter and block predicates on 7 tables, app role without DDL or policy rights, tested locally |
| RNF-02 | Offline capture, idempotent operations | in progress | Idempotency-Key replay store tested; PWA queue pending |
| RNF-03 | Intune-managed Android, PWA-capable browser | unverified | needs device |
| RNF-04 | 5-year retention | not started | |
| RNF-05 | PDF ≤ 50 pages, ≤ 150 MB | tested locally | Validation tests (51 pages rejected, size limit, encrypted) |
| RNF-06 | Store UTC, show Mexico City | in progress | UTC storage and FECHA conversion tested; UI formatting helper in @pipeline/ui |
| RNF-07 | Audit every write and download | tested locally | Download audit committed before streaming |
| RNF-08 | Initial list < 3 s on 4G | unverified | needs device |

## User stories

| HU | Story | Status | Evidence |
|---|---|---|---|
| HU-01 | Sign in with corporate account | in progress | Dev issuer sign-in tested in Playwright (PWA and admin); MSAL provider written and type-checked, unverified against a tenant |
| HU-02 | See only my sites | in progress | Backend done and tested; PWA pending |
| HU-03 | Load CSV/XLSX/XLS and preview | tested locally | Playwright `admin.cargas.spec.ts` |
| HU-04 | Approve or exclude doubtful rows | tested locally | Playwright `admin.cargas.spec.ts` |
| HU-05 | Manage equivalences | tested locally | Playwright `admin.equivalencias.spec.ts` |
| HU-06 | Site detail | in progress | Backend tested; PWA pending |
| HU-07 | Capture contact, advance to Dueño Localizado | in progress | Backend tested; PWA pending |
| HU-08 | Capture measurements, advance to Primera visita | in progress | Backend tested; PWA pending |
| HU-09 | Upload PDFs, advance to Recepción de documentos | in progress | Backend tested; PWA pending |
| HU-10 | Work offline, auto sync | not started | |
| HU-11 | Resume interrupted upload | in progress | Backend tested (lost part, resume state); PWA pending |
| HU-12 | Upload photos | in progress | Backend tested; PWA pending |
| HU-13 | Admin return with reason | tested locally | Playwright `admin.sitios.spec.ts` |
| HU-14 | Teams notice on return | in progress | Outbox + in-app notice backend tested; Teams delivery unverified |
| HU-15 | Audit log viewer | tested locally | Playwright `admin.auditoria.spec.ts` (filter by action, detail JSON) |
| HU-16 | Documents in Fabric with metadata | in progress | Metadata and documents container path tested locally; OneLake shortcut and Mirroring statically validated only |
| HU-17 | Purge after 5 years | in progress | Job tested locally; immutability and legal hold unverified |
| HU-18 | Pen test and RLS tests before production | not started | |

## Infrastructure and operations

| Item | Status | Evidence |
|---|---|---|
| Local stack (compose: SQL Server, Azurite, dev IdP, API, scheduler) | implemented | `make up`; health and readiness verified |
| Alembic baseline with RLS, ledger, app user | tested locally | `backend/migrations/versions/1130828e690d_baseline.py`; downgrade and upgrade cycle verified |
| Bicep templates per `AZURE_DESIGN.md` | statically validated | 13 modules + 3 param files, `bash infra/bicep/validate.sh` passes; nothing deployed |
| GitHub Actions CI/CD | statically validated | ci, build-deploy, deploy-environment, drift; actionlint clean; never executed on GitHub |
| Observability (structured logs, correlation, App Insights) | implemented | JSON logs, correlation id header, forbidden-field redaction; App Insights wiring unverified locally |
| Local development guide verified from clean clone | not started | |
