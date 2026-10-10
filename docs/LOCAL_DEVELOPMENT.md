# Local development

Everything runs on one machine without Azure credentials. The stack reproduces the production
architecture with local substitutes (see `ENVIRONMENTS.md` for the differences).

## Prerequisites

| Tool | Version used | Notes |
|---|---|---|
| Docker Engine + Compose v2 | 29 / 2.27 | Runs SQL Server 2022, Azurite, the dev identity provider, the API and the scheduler |
| Node.js | 22 | `corepack enable pnpm` gives pnpm 12 (pinned in `package.json`) |
| Python | 3.12 | Only for `samples/generate_sample.py`; the API itself runs in Docker (needs the Microsoft ODBC driver, which the image installs) |
| make, curl | any | |
| Bicep CLI | optional | `make bicep-lint`; install from GitHub releases into `~/.local/bin` |

Disk: about 3 GB for images, 1 GB for `node_modules`, 200 MB for Playwright Chromium.

## First run

```bash
cp .env.example .env            # dev-only values; never used in Azure
make up                         # builds images, starts the stack, applies migrations, checks health
make db-seed                    # 10 equivalences + 87 synthetic sites through the real bulk-load path
corepack enable pnpm && pnpm install
pnpm dev                        # PWA at http://localhost:5173, admin at http://localhost:5174
```

Sign in with the development user picker: `ard` to `jdc` are coordinators, `adm` is the admin,
`xna` has no role (useful to test the 403 path). Tokens are real RS256 JWTs from
`tools/dev-idp`, validated by the API exactly as Entra tokens would be.

What `make up` does, in order: `db-init` (creates the `pipeline` database and the least-privilege
login `pipeline_app`), `alembic upgrade head` (schema, RLS policy, ledger tables, role grants,
catalogs), then the API with hot reload and the scheduler that runs the background jobs.

## Daily commands

| Command | Purpose |
|---|---|
| `make up` / `make down` | Start or stop the stack (data kept) |
| `make reset` | Stop and delete all local data (database, blobs, dev signing key) |
| `make logs` | Tail API and scheduler JSON logs |
| `make health` | Liveness (`/healthz`) and readiness (`/readyz`: database + storage) |
| `make db-migrate` | Apply migrations after pulling schema changes |
| `make db-shell` | `sqlcmd` on the local database as `sa` |
| `make test` | Backend unit + integration tests against the running stack |
| `make test-unit` | Backend unit tests only |
| `make lint` | ruff, mypy strict, eslint, tsc |
| `make e2e` | Playwright end-to-end tests (needs `pnpm dev` running) |
| `make job-promote`, `make job-outbox`, `make job-purge`, `make job-expire_uploads`, `make job-idempotency_cleanup` | Run one background job once |
| `make openapi` | Export `docs/openapi.json`; then `pnpm gen:api` regenerates the TypeScript client types |
| `make bicep-lint` | Static validation of the Azure templates |

Frontend only: `pnpm --filter pwa-coordinador test`, `pnpm --filter web-admin build`, etc.
Alternative without Node on the host: `make up-web` runs both Vite servers in containers.

## Creating a migration

```bash
# edit backend/app/models.py, then:
docker compose run --rm --no-deps --user $(id -u):$(id -g) -e HOME=/tmp -e DB_HOST=sqlserver api \
  alembic revision --autogenerate -m "describe change"
make db-migrate
```

Ledger tables, RLS predicates and grants are raw SQL in the baseline migration; autogenerate
never manages them. Migrations must stay backward compatible with the running revision
(expand and contract) because production rollback is a traffic shift, not a downgrade.

## Resetting data safely

`make reset` removes the Docker volumes. `make up && make db-seed` rebuilds the same state in
about two minutes. Blobs in Azurite are deleted with the volume; nothing is shared with Azure.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `make up` hangs on sqlserver health | First start of SQL Server takes 20 to 40 s. Check `docker compose logs sqlserver`. On low memory the container exits: SQL Server needs about 2 GB. |
| `/readyz` returns 503 with `database: error` | Migrations not applied or password mismatch between `.env` and the running container. Run `make reset && make up` if you changed `SQL_SA_PASSWORD` after the first start (the password is baked into the volume). |
| API returns 401 for every request | The dev IdP restarted with a new key and the SPA holds a token signed by the old key. Sign out and in again. Keys persist in the `devidpkeys` volume, so this only happens after `make reset`. |
| 500 on a query with `IS 1` in the SQL | SQL Server does not accept `IS TRUE`. Use `== true()` with SQLAlchemy, never `.is_(True)`. |
| `Connection is busy with results for another command` | pyodbc has no MARS: materialize `.scalars()` into a list before issuing another query on the same session. |
| Permission denied writing files from a container | The image runs as uid 10001. Commands that write to the bind mount (alembic revision, ruff, pytest cache) must run with `--user $(id -u):$(id -g)`; the Makefile does this. |
| Vite shows the app but API calls fail with CORS | Use the Vite dev server URL (5173/5174), not the API port. The app only talks to `/api` on its own origin. |
| Playwright cannot find Chromium | `pnpm --filter e2e exec playwright install chromium` |
| Port 1433, 8000, 8001, 10000, 5173 or 5174 in use | Override `SQL_PORT`, `API_PORT`, `DEV_IDP_PORT`, `AZURITE_PORT` in `.env`; Vite ports in `apps/*/package.json`. |

## Inspecting data

```bash
make db-shell
1> SELECT id, nombre, estatus, usuario_codigo FROM sitio WHERE vigente = 1;
2> GO
```

RLS is bypassed for `sa` (db_owner). To see what a coordinator sees, run
`EXEC sp_set_session_context 'oid', '<oid>'; EXEC sp_set_session_context 'rol', 'Coordinador';`
first in the same session, or use the API.

Blobs: the Azurite data lives in the `azuritedata` volume; use Azure Storage Explorer against
`http://localhost:10000/devstoreaccount1` with the well-known Azurite key from `.env.example`.
