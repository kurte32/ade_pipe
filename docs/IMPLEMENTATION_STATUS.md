# Implementation status

Updated: 2026-10-10 (baseline). Statuses: `not started` · `in progress` · `implemented` · `tested locally` (automated test executed and passing) · `statically validated` (lint/build only, no runtime) · `unverified` (needs Azure or a device) · `blocked` (external dependency).

## Baseline findings (Phase One)

- Repository before this build: two PDFs, one review, `architecture/`. No code, tests, CI, or infrastructure.
- Development machine: Ubuntu (kernel 6.8), 16 CPU, 62 GB RAM, 23 GB free disk. Docker 29 + Compose 2.27, Node 22.23 + pnpm 12 (corepack), Python 3.12 + uv, make, gh. No ODBC driver on the host, no Azure CLI. Standalone Bicep CLI installed under `~/.local/bin`.
- Local substitutes verified by probe on 2026-10-10: SQL Server 2022 (CU27) supports `SESSION_CONTEXT` and append-only ledger tables (UPDATE rejected with error 37359). Azurite supports block staging, block list, blob index tags, server-side copy, and range reads.
- Chrome extension (Claude in Chrome) is **not connected** in this session. Browser workflow validation uses Playwright with headless Chromium; this is recorded as such and is not claimed as Chrome extension validation.
- The TDD's sample file `pipeline_nacional_mx_20261009.xlsx` is not available. A synthetic file matching Anexo A is generated into `samples/`.

## Requirements

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| RF-01 | Coordinator signs in with corporate Entra account from mobile | not started | |
| RF-02 | Coordinator lists and views only assigned sites | not started | |
| RF-03 | One-step status advance with minimum requirements | not started | |
| RF-04 | Capture contact, measurements with photos, required documents | not started | |
| RF-05 | Admin bulk load CSV/XLSX/XLS with preview, warnings, approval | not started | |
| RF-06 | Admin returns a site to an earlier status with mandatory reason | not started | |
| RF-07 | Teams notification on return | not started | |
| RF-08 | Chunked resumable PDF upload, validation, storage | not started | |
| RF-09 | Admin manages user→email equivalences and reassignment | not started | |
| RF-10 | Immutable audit log | not started | |
| RF-11 | 5-year retention and audited purge | not started | |
| RNF-01 | Isolation at API, service, DB; encryption; no secrets in code | not started | |
| RNF-02 | Offline capture, idempotent operations | not started | |
| RNF-03 | Intune-managed Android, PWA-capable browser | unverified | needs device |
| RNF-04 | 5-year retention | not started | |
| RNF-05 | PDF ≤ 50 pages, ≤ 150 MB | not started | |
| RNF-06 | Store UTC, show Mexico City | not started | |
| RNF-07 | Audit every write and download | not started | |
| RNF-08 | Initial list < 3 s on 4G | unverified | needs device |

## User stories

| HU | Story | Status | Evidence |
|---|---|---|---|
| HU-01 | Sign in with corporate account | not started | |
| HU-02 | See only my sites | not started | |
| HU-03 | Load CSV/XLSX/XLS and preview | not started | |
| HU-04 | Approve or exclude doubtful rows | not started | |
| HU-05 | Manage equivalences | not started | |
| HU-06 | Site detail | not started | |
| HU-07 | Capture contact, advance to Dueño Localizado | not started | |
| HU-08 | Capture measurements, advance to Primera visita | not started | |
| HU-09 | Upload PDFs, advance to Recepción de documentos | not started | |
| HU-10 | Work offline, auto sync | not started | |
| HU-11 | Resume interrupted upload | not started | |
| HU-12 | Upload photos | not started | |
| HU-13 | Admin return with reason | not started | |
| HU-14 | Teams notice on return | not started | |
| HU-15 | Audit log viewer | not started | |
| HU-16 | Documents in Fabric with metadata | not started | |
| HU-17 | Purge after 5 years | not started | |
| HU-18 | Pen test and RLS tests before production | not started | |

## Infrastructure and operations

| Item | Status | Evidence |
|---|---|---|
| Local stack (compose: SQL Server, Azurite, dev IdP, API, scheduler) | in progress | |
| Alembic baseline with RLS, ledger, app user | not started | |
| Bicep templates per `AZURE_DESIGN.md` | not started | |
| GitHub Actions CI/CD | not started | |
| Observability (structured logs, correlation, App Insights) | not started | |
| Local development guide verified from clean clone | not started | |
