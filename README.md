# ade_pipe

Pipeline de Posibles Tiendas: regional coordinators manage candidate store sites from managed Android devices (offline-first PWA), and an administrator loads sites in bulk, reviews quality, returns sites with a reason, and manages equivalences and the audit log. Backend on FastAPI and Azure SQL (Row-Level Security, ledger audit), documents in Blob storage exposed to Fabric, identity with Microsoft Entra ID.

## Quick start (local, no Azure account needed)

```bash
cp .env.example .env
make up            # SQL Server 2022, Azurite, local OIDC issuer, API (+ migrations), scheduler
make db-seed       # 10 dev coordinators and 87 synthetic sites
corepack enable pnpm && pnpm install
pnpm dev           # PWA http://localhost:5173 · admin http://localhost:5174
make test && make e2e
```

Sign in with the development user picker (`ard` to `jdc` coordinators, `adm` admin). Details, troubleshooting and every command: `docs/LOCAL_DEVELOPMENT.md`.

## Repository map

| Path | Content |
|---|---|
| `apps/pwa-coordinador`, `apps/web-admin` | React apps (Vite). Shared packages in `packages/` (auth, api-client, ui) |
| `backend/` | FastAPI modular monolith, Alembic migrations, tests |
| `tools/dev-idp` | Local OIDC issuer for development (never deployed) |
| `infra/bicep` | Azure infrastructure as code (statically validated) |
| `.github/workflows` | CI, build and deploy, drift detection |
| `e2e/` | Playwright end-to-end tests |
| `architecture/` | Target architecture, Azure design, security, ADRs, plan, risks, production readiness |
| `docs/` | Local development, operations, environments, Azure deployment, implementation status, delivery report, OpenAPI |
| `samples/` | Synthetic load file generator and files |
| `*.pdf`, `Propuesta_mejoras_TDD_v0.1.md` | Source design documents (Spanish) and the design review |

Status of the build and what is verified: `docs/IMPLEMENTATION_STATUS.md` and `docs/DELIVERY_REPORT.md`.
