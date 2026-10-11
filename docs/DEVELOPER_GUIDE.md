# Developer guide · Pipeline de Posibles Tiendas

Date: 11 October 2026 · Branch `ux-redesign` · **Audience:** engineers joining or maintaining the
codebase · **When to read:** first day, and before touching a module you have not worked in ·
**Source of truth:** the code; `docs/CONVENTIONS.md` for the rules this guide assumes.

## 1. First day

1. Read `README.md`, then this guide, then `docs/CONVENTIONS.md` (rules) and
   `docs/GLOSSARY.md` (the Spanish nouns you will see everywhere).
2. Run the stack: `cp .env.example .env && make up && make db-seed`, then
   `corepack enable pnpm && pnpm install && pnpm dev` (Node 22; with nvm,
   `nvm use 22` first). Details and troubleshooting: `docs/LOCAL_DEVELOPMENT.md`.
3. Sign in at `http://localhost:5173` as `ard` (coordinator) and `http://localhost:5174` as
   `adm` (admin). Walk the two workflows once: advance a site in the PWA, return it in the admin.
4. Run the gates: `make test` (backend), `pnpm -r test` (frontend units), `make e2e` (Playwright,
   needs `pnpm dev` running), `make lint`.
5. Skim `architecture/TO_BE.md` sections 1 to 6 for the why, and `docs/API_GUIDE.md` for the
   contract.

## 2. Repository map

```text
backend/app/core        config, db (session context + RLS), security (JWT), errors (Problem Details),
                        idempotency, limits, logging, telemetry, storage (BlobStore), clock
backend/app/modules     identity, sitios, transiciones (+rules.py), cargas (parser, validation),
                        archivos (upload sessions, scan, promotion), notificaciones (outbox, graph),
                        auditoria, equivalencias (directory)      each: router / service / schemas
backend/app/jobs        promote, outbox, expire_uploads, purge, idempotency_cleanup, scheduler, run
backend/app/cli.py      db-init, seed, openapi, e2e-cleanup
backend/migrations      Alembic; baseline holds RLS, ledgers, grants, catalog seeds (raw SQL)
backend/tests           unit/ (no DB) and integration/ (compose stack)
apps/pwa-coordinador    React PWA: pages, components, sync/ (engine, context), upload/, db/ (Dexie)
apps/web-admin          React admin: pages, lib/
packages/ui             design tokens (base.css), shared components, label maps
packages/auth           AuthProvider: dev (tools/dev-idp) and msal; runtime config.json loading
packages/api-client     typed fetch wrapper, Problem Details parsing, generated OpenAPI types
e2e                     Playwright: global setup builds a site pool through the real bulk load
tools/dev-idp           local OIDC issuer (RS256, Entra v2 claims), users.json
infra/bicep             Azure IaC (13 modules), params per environment, validate.sh
.github/workflows       ci, build-deploy, deploy-environment (reusable), drift
docs/, architecture/    see docs/README.md
```

## 3. How a request flows

1. Front Door (Azure) or the Vite proxy (local) sends `/api/*` to FastAPI.
2. `core/limits.py` rejects bodies over `MAX_REQUEST_BYTES` (413, before anything else).
3. `core/logging.py` middleware generates the correlation id, binds `route` and `method`.
4. `core/security.py` validates the bearer token (`get_claims`) and `require_role` checks the
   role. The caller's identity is always the `oid` claim.
5. `core/db.py` hands out a session whose connection already ran `sp_set_session_context`
   with `oid` and `rol`; SQL Server row-level security filters every query from then on. Jobs use
   the all-zero `SYSTEM_OID` with role `Sistema`.
6. The router validates the body (Pydantic) and calls the module service; the service enforces
   business rules, writes, appends to `auditoria` in the same transaction, and returns a schema.
7. `core/errors.py` turns `AppError`, validation errors, `StaleDataError` (412) and unhandled
   exceptions into Problem Details with the correlation id.

Writes that the PWA can replay carry `Idempotency-Key`; `core/idempotency.run_once` claims the
key before the work and stores the response after it (`docs/API_GUIDE.md` §3).

## 4. How the PWA stays correct offline

The sync engine (`apps/pwa-coordinador/src/sync/engine.ts`) is the most delicate code in the
repository. Read its unit tests first (`engine.test.ts`); they encode the invariants.

- **Local state** lives in Dexie (`db/schema.ts`): `sitios` (cached `SitioDetail` + ETag),
  `operaciones` (the queue), `fotos` (blobs), `meta` (watermark, last sync, ETag successors,
  upload sessions).
- **One FIFO chain per site.** Operations are ordered by `seq`; a `bloqueada` or `error` op halts
  only that site's chain until the user retries or discards it in the conflict panel.
- **ETag chaining.** Only transitions send `If-Match`. When a queued transition was created while
  an earlier write was in flight, the engine follows the successor map (`sync.etagSuccessors`)
  so the server sees the ETag it produced, never a stale one (risk R24). Changes by other actors
  still produce a 412, which is the intended conflict.
- **Failure classes.** 412/422/404/409/428/410 → `bloqueada` with the server's `current` and
  `faltantes`; 429/5xx → retried up to `MAX_TRANSIENT_RETRIES = 5`; offline or 401 → back to
  `pendiente`, sync stops, banner shown.
- **Delta pull** after a successful push: `GET /sitios/delta?desde=&conocidos=`; `removed_ids`
  deletes sites the coordinator can no longer see.
- **Sync triggers:** every 30 s when online, the `online` event, every enqueue, and the sync
  chip. The service worker never syncs (it cannot obtain tokens).
- **"Salir" clears everything local, including unsent captures.** `Shell` asks for confirmation
  when `pendingCount + blockedCount > 0` (dialog `dialog-salir`, e2e `pwa.salir.spec.ts`); any
  other flow that signs the user out must do the same.

Uploads: PDFs use the resumable session protocol online only (`upload/resumable.ts`, session id
and hash kept in `meta` so a cut upload resumes); photos are compressed on the phone
(`lib/photos.ts`, 1,600 px edge, JPEG quality steps down to 0.5) and go through the queue.

## 5. Recipes

### Add an API endpoint

1. Schema in `modules/<m>/schemas.py`; rule in `service.py`; route in `router.py` with
   `Depends(require_role("…"))` and `get_session`. Raise `AppError(status, slug, title, detail,
   extra)`; never return exception text.
2. Call `auditoria.record(session, claims, accion, entidad, entidad_id, detalle)` inside the
   transaction for every write or download.
3. If the PWA will replay it, accept `Idempotency-Key` through `run_once`; if it changes a site,
   return the new ETag in the body and header.
4. Tests: a unit test if there is pure logic, an integration test in `tests/integration` marked
   `@pytest.mark.integration`, and an RLS case if the endpoint touches coordinator data.
5. `make openapi && pnpm gen:api`, then use `components["schemas"]["…"]` in the frontend.
6. Document the endpoint in `docs/API_GUIDE.md` and, if the UI shows a new code, add its label
   to `packages/ui/src/labels.ts`.

### Add a migration

See `docs/DATA_MODEL.md` §6. Expand-and-contract only; a new coordinator-data table needs
`coordinador_oid`, the RLS policy entry and a test in `test_identity_and_rls.py`.

### Add a catalog value (status, reason, document type)

Catalog rows are seeded by the baseline migration; add a new migration with an `INSERT`, never
edit the baseline. The UI reads labels from `GET /catalogos`, so nothing changes in the frontend
unless the value needs a tone (`estatusTone` in `packages/ui/src/EstatusBadge.tsx`).

### Add a page or component

1. Compose from `packages/ui`: `PageHeader`, `Alert`, `Field`, `Modal`, `EmptyState`, `Icon`,
   `EstatusBadge`, `StageIndicator`; tokens from `base.css`. No inline colours or sizes
   (`docs/ux/DESIGN_SYSTEM.md`).
2. Set `usePageTitle("…")`; keep one `h1`; give every control an accessible name.
3. Data through TanStack Query (`useApi()`); offline-aware pages in the PWA read Dexie and only
   call the API when `useSync().online`.
4. Translate every API code through `labels.ts` or the catalogs.
5. Add or extend a Playwright spec; keep the `data-testid`s listed in
   `docs/ux/UX_VALIDATION.md` stable (the memory of load-bearing selectors is in that file's
   section 2).

### Add a background job

Create `backend/app/jobs/<name>.py` with a `run(settings)` function that is safe to rerun, register
it in `jobs/run.py` and the local `scheduler.py` interval table, add a Container Apps Job in
`infra/bicep/modules/containerapps.bicep` with its cron, and a line in `docs/OPERATIONS.md`.

### Add an e2e test

Use only pool sites (`helpers/pool.ts`, origen ids 890000 to 890011) or ids in the 800000 range;
`global-setup` rebuilds the pool through the real bulk load and `e2e-cleanup` removes them.
Spec names must match `pwa.*.spec.ts` or `admin.*.spec.ts` (Playwright projects).

## 6. Debugging

| Symptom | Where to look |
|---|---|
| API error in the UI | The alert shows `Referencia: <correlation id>`; `make logs` (local) or KQL on `ContainerAppConsoleLogs_CL` with that id; the audit row with that `correlation_id` shows the write it belonged to |
| 412 on a transition | Compare `If-Match` with `GET /sitios/{id}` ETag; check `sitio_estatus_historial` for an admin return in between |
| Coordinator cannot see a site | `SELECT coordinador_oid, vigente FROM sitio WHERE origen_id = …`; RLS hides other owners and non-vigente sites, the API returns 404 |
| Upload stuck | `subida_sesion.estado`; `SCAN_MODE`; the `promote` job (`make job-promote`); `docs/OPERATIONS.md` RB-02 |
| PWA shows stale sites | Sign out clears the cache (after syncing); check `meta.sitios.maxRowversion` in DevTools → Application → IndexedDB |
| Test flakiness | Backend tests run in random order (`pytest -p randomly --randomly-seed=<seed>` reproduces); Playwright traces in `e2e/test-results` |
| Local SQL quirks | `== true()` not `.is_(True)`; materialise `.scalars()` before a second query (no MARS) |

## 7. Quality gates (what CI runs)

`ci.yml`: backend (ruff, ruff format, mypy strict on `app`, pip-audit, pytest against SQL Server
2022, Azurite and the dev IdP), frontend (eslint, tsc, vitest, build, pnpm audit), e2e
(Playwright against `make up` + `pnpm dev`), gitleaks, Bicep build/lint, actionlint. Every action
is pinned to a commit SHA. Locally: `make lint && make test && pnpm -r test && make e2e`.

Test counts on this branch: backend 183 (111 unit, 72 integration; `pytest --collect-only -q -m integration`), frontend 40, Playwright 18. CI also runs `alembic check` after the upgrade.
Every file under `tests/integration/` carries `pytestmark = pytest.mark.integration`, so
`make test-unit` runs without the stack; keep the marker when adding a file there.

## 8. Things that are easy to get wrong

- **`with_for_update()` renders nothing on SQL Server.** SQLAlchemy's mssql dialect silently drops
  it. A row lock is a table hint: `select(Sitio).with_hint(Sitio, "WITH (UPDLOCK, ROWLOCK)")`,
  and `READPAST` to skip rows another worker holds (the outbox claim). The audit found four
  no-op locks this way; the HTTP burst test in `test_concurrency.py` is the guard.
- **Lock, then re-read, then check the precondition.** A request that waited on the lock must
  compare `If-Match` against the version the winner wrote, so `session.refresh(sitio)` comes
  before `_require_if_match` (see `transiciones.avanzar`).
- **Changing a site's owner means every owner-scoped row.** Use `sitios.cambiar_propietario`; never
  assign `coordinador_oid` on the site alone (bulk reload used to, audit DAT-1).
- **Writes outside `sitio` that change the site must touch it** (`_lock_sitio` in archivos),
  otherwise other devices never receive the change through the delta.
- **The PWA store belongs to one account.** `ensureOwner` clears it on an account change; any new
  table in Dexie must be cleared in `clearLocalData` too.
- **Every `api-client` request has a 30 s timeout** (`timeoutMs` to override). A timeout is a
  transient `NetworkError`; the caller's own abort is rethrown.

- Reading the coordinator from a request parameter instead of `claims.oid`.
- Forgetting `auditoria.record` in a write path, or logging names, phones, emails, tokens or
  bodies (the redaction list in `core/logging.py` is a safety net, not a licence).
- Editing the baseline migration; adding a table with coordinator data without RLS.
- Changing a visible string or a `data-testid` that a Playwright spec relies on.
- Putting colours or sizes inline instead of in `packages/ui`.
- Assuming the service worker can sync or that `localStorage` survives "Salir".
- Treating `Sin estatus` (potencial) as missing data; it is a legitimate business value.
