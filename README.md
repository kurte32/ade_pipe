# Pipeline de Posibles Tiendas

Store-site pipeline for Tiendas 3B. Regional coordinators work candidate store sites from managed
Android devices with an offline-first PWA; an administrator loads sites in bulk, reviews quality,
returns sites with a reason, and manages coordinator equivalences and the audit log. The backend is
a FastAPI modular monolith on SQL Server / Azure SQL with Row-Level Security and ledger (append-only)
audit tables; documents live in Blob storage exposed to Microsoft Fabric; identity is Microsoft
Entra ID.

**Where it stands (11 October 2026).** Every gate that can run without an Azure subscription is
green on the production artefacts (container image and built PWA); the first deployment to Azure has
not happened yet and needs the prerequisites listed in `docs/RELEASE_READINESS.md` §4. Nothing in
this repository is described as running in Azure until it has.

## Contents

- [What it does](#what-it-does)
- [Architecture at a glance](#architecture-at-a-glance)
- [Quick start](#quick-start)
- [Everyday commands](#everyday-commands)
- [Quality gates](#quality-gates)
- [Configuration and environments](#configuration-and-environments)
- [Deployment](#deployment)
- [Repository map](#repository-map)
- [Documentation](#documentation)
- [Conventions](#conventions)
- [What is still open](#what-is-still-open)

## What it does

Two roles, two applications, one API.

**Coordinador (PWA, phone).** Sees only their own sites (enforced by RLS, not by the UI). Advances
each site through the fixed sequence `sitio_prospectado` → `dueno_localizado` → `primera_visita` →
`recepcion_documentos`, capturing the owner's contact, the visit measurements and photos, and the
documents (PDF). Works fully offline: captures queue locally (Dexie), replay when the network
returns, with per-site ETags to detect conflicts. Can propose a discard; receives returns and
notices in an in-app feed (and in Teams when Graph is configured).

**Administrador (web, desktop).** Loads sites in bulk from the national `.xlsx`/`.csv`
(validated, staged, confirmed as a lot), reviews the review queue, returns a site with a reason,
reassigns sites between coordinators, manages the coordinator-to-region equivalences, and reads the
audit ledger. Dashboard queues and the audit log are server-side.

**Background jobs.** `promote` (scanned uploads become the current document), `outbox` (Teams and
in-app notices), `expire_uploads`, `purge` (retention), `idempotency_cleanup`. Locally they run in
the `scheduler` compose service; in Azure as Container Apps Jobs.

**Guarantees the code enforces.** Row-Level Security by session context (oid, role) on every
query; append-only ledger tables for audit, transitions and loads; optimistic concurrency with
rowversion ETags (`If-Match` → 412/428); idempotency keys on writes; resumable, hash-verified
uploads; malware scan before promotion; per-user rate limits; Problem Details (RFC 9457) errors
with a correlation id on every response.

## Architecture at a glance

```text
 Android (Intune)                 Browser (desktop)
 ┌──────────────────┐             ┌──────────────────┐
 │ pwa-coordinador  │             │ web-admin        │        React 19 · Vite 6 · TanStack Query
 │ offline store    │             │                  │        packages/ui · packages/auth (MSAL)
 └────────┬─────────┘             └────────┬─────────┘        packages/api-client (typed, generated)
          │  HTTPS, bearer (Entra)          │
          └──────────────┬──────────────────┘
                         ▼
             Azure Front Door (WAF, two hosts) ── Static Web Apps (SPA bundles)
                         │  X-Azure-FDID validated by the API
                         ▼
             Azure Container Apps · pipeline-api (FastAPI) · Jobs (scheduler)
              ├── Azure SQL Database  (RLS, ledger tables, Alembic migrations)
              ├── Blob staging ──scan──► ADLS Gen2 documents ──► OneLake shortcut (Fabric)
              ├── Microsoft Graph (Teams activity feed, directory)
              └── Key Vault · managed identities · Log Analytics · Application Insights
```

| Layer | Technology |
|---|---|
| Frontends | React 19, TypeScript, Vite 6, React Router 7, TanStack Query 5, Dexie 4 (PWA store), `vite-plugin-pwa` (Workbox), `hash-wasm` streaming SHA-256, MSAL Browser 4 |
| API | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, pyodbc, Pydantic 2, structlog, OpenTelemetry (Azure Monitor) |
| Data | SQL Server 2022 locally / Azure SQL Database; Azurite locally / Azure Blob + ADLS Gen2 |
| Identity | Microsoft Entra ID (RS256 JWT, roles, client-id binding); `tools/dev-idp` locally |
| Infrastructure | Bicep (14 modules), GitHub Actions (ci, build-deploy, deploy-environment, drift) |
| Tests | pytest (unit + integration), Vitest, Playwright (`pwa-mobile`, `admin-desktop`), axe-core |

Design rationale: `architecture/TO_BE.md`, `architecture/AZURE_DESIGN.md`, `architecture/SECURITY.md`
and the ten ADRs in `architecture/ADR/`.

## Quick start

Everything runs on one machine. No Azure account or credentials are needed.

**Prerequisites:** Docker Engine with Compose v2, Node.js 22 (`corepack enable pnpm` gives the pinned
pnpm 12), `make`, `curl`. Python 3.12 only if you want to regenerate the sample file. About 3 GB
for images, 1 GB for `node_modules`, 200 MB for Playwright's Chromium.

```bash
cp .env.example .env                   # development-only values; never used in Azure
make up                                # SQL Server 2022, Azurite, dev OIDC issuer, API (+ migrations), scheduler
make db-seed                           # 10 coordinator equivalences and 87 synthetic sites through the real bulk load
corepack enable pnpm && pnpm install
pnpm dev                               # PWA http://localhost:5173 · admin http://localhost:5174
```

Sign in with the development user picker: `ard` to `jdc` are coordinators, `adm` is the
administrator, `xna` has no role (exercises the 403 path). The tokens are real RS256 JWTs issued by
`tools/dev-idp` with Entra v2 claims and are validated by the API exactly as Entra tokens would be.

| Service | URL (local) |
|---|---|
| PWA coordinador | http://localhost:5173 |
| Web admin | http://localhost:5174 |
| API, OpenAPI UI (local only) | http://localhost:8000 · http://localhost:8000/api/docs |
| Health | http://localhost:8000/healthz · http://localhost:8000/readyz |
| Dev identity provider | http://localhost:8001 |
| SQL Server · Azurite | localhost:1433 · localhost:10000 |

Troubleshooting, data inspection and the test setup: `docs/LOCAL_DEVELOPMENT.md`. If you use nvm,
run `nvm use 22` before any `pnpm` or `make lint`/`make e2e` command.

## Everyday commands

| Command | What it does |
|---|---|
| `make up` / `make down` | Start or stop the stack, keeping data |
| `make reset` | Stop and delete all local data (database, blobs, dev signing key) |
| `make logs` · `make health` · `make ps` | Tail API and scheduler JSON logs · probe `/healthz` and `/readyz` · container status |
| `make db-migrate` · `make db-shell` | Apply Alembic migrations · `sqlcmd` on the local database |
| `make db-seed` | Reload the synthetic sample and the development data |
| `make test` · `make test-unit` | Backend tests against the stack · unit tests only |
| `pnpm -r test` | Frontend unit tests (Vitest) |
| `make lint` | ruff, mypy strict, eslint, tsc |
| `make e2e` | Playwright against the dev servers (needs `pnpm dev`) |
| `make e2e-preview` | Coordinator specs against the **built PWA** with the service worker, under the Static Web App security headers |
| `make e2e-image` | Full Playwright suite through the **production image** (no dev dependencies, non-root) |
| `make job-promote` · `job-outbox` · `job-purge` · `job-expire_uploads` · `job-idempotency_cleanup` | Run one background job once |
| `make openapi && pnpm gen:api` | Export `docs/openapi.json` and regenerate the TypeScript client types |
| `make bicep-lint` | Build and lint every Bicep template (no subscription needed) |

## Quality gates

What CI runs on every pull request, and what the local commands reproduce
(`docs/DEVELOPER_GUIDE.md` §7). Numbers are from the last run on this branch; the current evidence
table lives in `docs/RELEASE_READINESS.md` §2.

| Gate | Result on `ux-redesign` |
|---|---|
| Backend tests, coverage floor 80 % | 191 passed, 89 % |
| Frontend unit tests | 42 passed |
| Playwright on dev servers · built PWA under CSP · production image | 18 · 9 · 18 passed |
| Accessibility (axe, WCAG 2 A/AA, every page) | 0 serious or critical |
| Static analysis (ruff, mypy strict, eslint, tsc) | clean |
| Schema (`alembic upgrade`/`downgrade` cycle, `alembic check`) | clean |
| Bicep build and lint, actionlint, gitleaks, `pip-audit`, `pnpm audit` | clean |
| Image scan (Trivy, HIGH/CRITICAL) · OWASP ZAP baseline and authenticated API scan | 0 findings · 0 failures |

Also exercised locally and recorded in the readiness statement: mutation probes (10 of 10 caught),
restore drill with ledger verification, database outage simulation, latency sanity (p95 200 ms),
Lighthouse mobile (92 / 100 / 100 / 82), emulated 4G first list in 2.5 s.

## Configuration and environments

All configuration comes from the environment (`backend/app/core/config.py`). `.env.example`
documents every variable with its local value. Three environments share one codebase; only adapters
change (`docs/ENVIRONMENTS.md`).

| `ENVIRONMENT` | Where | Meaning |
|---|---|---|
| `local` | compose stack, CI | The only value that trusts the local SQL certificate, serves `/api/docs`, accepts the dev identity provider and allows `e2e-cleanup` |
| `test` | Azure dev and UAT | Deployed: Entra auth pinned to `login.microsoftonline.com`, managed identity to SQL, Azure storage, real tenant id, `AUTH_ADMIN_AZP` set |
| `production` | Azure prod | Everything `test` requires, plus Defender scanning, Graph notifications and directory, `FRONT_DOOR_ID` |

The image defaults to `ENVIRONMENT=production` and refuses to start with development settings, so a
container launched without configuration fails closed.

## Deployment

Azure is deployed from Bicep by GitHub Actions with OIDC federation (no stored cloud secrets):

```text
push main ──► build-deploy ──► ci ──► build (image → Trivy → ACR, SPA bundles) ──► deploy dev
tag release-x.y.z ───────────► ci ──► build ──────────┬─► deploy test
                                                      └─► deploy prod (required reviewers, same digest)
drift.yml (daily 05:00 UTC) ─► what-if against each environment, reports configuration drift
```

Images are promoted by digest, never rebuilt per environment. Rollback is a traffic shift to the
previous revision; migrations are expand-and-contract so the previous image runs on the new schema.
Procedure, first-deployment order, verification checklist and runbooks: `docs/RELEASE_PROCESS.md`,
`docs/AZURE_DEPLOYMENT.md`, `docs/OPERATIONS.md`.

The deploy workflows and templates are statically validated only. They have never run against a
subscription; `docs/RELEASE_READINESS.md` §5 lists what the first run verifies, in order.

## Repository map

```text
apps/pwa-coordinador     React PWA: pages, components, sync/ (engine, context), upload/, db/ (Dexie)
apps/web-admin           React admin: pages, lib/
packages/ui              design tokens (base.css), shared components, label maps
packages/auth            AuthProvider: dev (tools/dev-idp) and MSAL; runtime config.json
packages/api-client      typed fetch wrapper, Problem Details parsing, generated OpenAPI types
backend/app/core         config, db (session context + RLS), security (JWT), errors, idempotency,
                         limits, ratelimit, edge (Front Door), logging, telemetry, storage
backend/app/modules      identity, sitios, transiciones, cargas, archivos, notificaciones,
                         auditoria, equivalencias   (each: router / service / schemas)
backend/app/jobs         promote, outbox, expire_uploads, purge, idempotency_cleanup, scheduler
backend/migrations       Alembic; the baseline holds RLS, ledgers, grants and catalog seeds
backend/tests            unit/ (no database) and integration/ (compose stack)
e2e/                     Playwright suite and tools (screenshots, network timing)
tools/dev-idp            local OIDC issuer (RS256, Entra v2 claims), users.json
infra/bicep              Azure IaC: main.bicep, 14 modules, params per environment, validate.sh
.github/workflows        ci, build-deploy, deploy-environment (reusable), drift
samples/                 synthetic load file generator and files (Anexo A layout)
architecture/            AS-IS, TO-BE, Azure design, security, ADRs, plan, risks, readiness
docs/                    guides, API, data model, operations, deployment, backlog, audit, UX
CHANGELOG.md             what shipped, by branch and date
*.pdf, Propuesta_mejoras_TDD_v0.1.md   source design documents (Spanish) and the design review
```

## Documentation

Start at `docs/README.md`, which indexes every document by the question it answers. The short
version, by role:

| You are… | Read |
|---|---|
| A new engineer | `docs/DEVELOPER_GUIDE.md`, `docs/CONVENTIONS.md`, `docs/GLOSSARY.md`, `docs/API_GUIDE.md`, `docs/DATA_MODEL.md`, `docs/ux/DESIGN_SYSTEM.md` |
| Support (L1/L2) | `docs/SUPPORT_GUIDE.md`, then `docs/OPERATIONS.md` runbooks |
| Release manager or TI | `docs/RELEASE_READINESS.md`, `docs/RELEASE_PROCESS.md`, `docs/AZURE_DEPLOYMENT.md`, `docs/ENVIRONMENTS.md` |
| Architect, security or business owner | `architecture/README.md`, `docs/audit/README.md` (independent audits and remediation), `docs/IMPROVEMENT_BACKLOG.md` §6 (decisions pending) |
| Curious about the UX | `docs/ux/UX_AUDIT.md`, `docs/ux/UX_VALIDATION.md`, screenshots in `docs/ux/screenshots/` |

Historic build records (10 October 2026): `docs/IMPLEMENTATION_STATUS.md` and
`docs/DELIVERY_REPORT.md`. The current statement of what is verified is `docs/RELEASE_READINESS.md`.

## Conventions

- **Language.** Documentation and code comments in English; Spanish domain nouns verbatim
  (`sitio`, `carga`, `devolución`, `coordinador`); every user-facing string in Spanish.
- **Branches and releases.** Feature branches merge into `main` by pull request with CI green.
  Tags `release-x.y.z` trigger the test and production deployments. `CHANGELOG.md` is the only
  history; `docs/IMPROVEMENT_BACKLOG.md` is the only to-do list.
- **Definition of done.** Behaviour change ships with its test (pytest, Vitest or Playwright);
  endpoint change regenerates `docs/openapi.json` and the client types; schema change ships as an
  expand-and-contract Alembic migration; documentation changes in the same pull request. Full list
  in `docs/RELEASE_PROCESS.md` §2 and `docs/CONVENTIONS.md`.
- **Nothing is claimed as verified in Azure until it has run there.** Every document states a
  fact's status: verified locally, statically validated, or not verified in Azure.

## What is still open

Tracked with owners in `docs/IMPROVEMENT_BACKLOG.md`. In short:

- **Azure prerequisites** (subscription, Entra registrations and real GUIDs in the parameter files,
  OIDC federation and environment secrets, SQL administrator group, Graph and Teams app,
  Defender, immutability policy) and then the first `build-deploy` run.
- **Acceptance on the deployed environment:** penetration test, Intune device test, real 4G
  measurement, forcing each alert once.
- **Assets and inputs from the business:** the official logo, a real legacy `.xls` load file, a
  manual screen-reader pass, and the decisions in backlog §6 (`entregado` status, `If-Match` on
  offline captures, catalogue values, retention event, privacy notice).
