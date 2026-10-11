# Engineering conventions

These rules apply to every module and app. They exist so that code written in parallel fits together.

## Repository layout

```
apps/pwa-coordinador      React PWA for coordinators (Vite, MSAL or dev auth, Dexie, Workbox)
apps/web-admin            React admin web (Vite)
packages/auth             Auth provider interface + MSAL and dev implementations
packages/api-client       Typed client generated from backend OpenAPI, plus request helpers
packages/ui               Shared components
backend/app               FastAPI application (modular monolith)
backend/app/core          config, db, security, errors, telemetry, storage, clock
backend/app/modules/<m>   router.py, service.py, repository.py, schemas.py, models.py (per module)
backend/app/jobs          CLI entrypoints for background jobs + local scheduler loop
backend/migrations        Alembic (raw SQL for RLS, ledger, grants)
backend/tests             unit/ (no DB), integration/ (real DB + Azurite), fixtures
tools/dev-idp             Local OIDC issuer for development
e2e                       Playwright tests against the running stack
infra/bicep               Bicep modules + parameter files per environment
.github/workflows         CI/CD
samples                   Synthetic load files
docs                      Operational docs and status
```

Ownership while working in parallel: a module owner edits only its directory. Shared files (`pyproject.toml`, `app/main.py` router registration, `docker-compose.yml`, root `package.json`, `Makefile`) are edited by the integrator; request changes in your final report instead of editing them.

## Backend

- Python 3.12, FastAPI, SQLAlchemy 2 (sync engine, `Session` per request), Pydantic v2 schemas, Alembic.
- Modules: `identity`, `sitios`, `transiciones`, `cargas`, `archivos`, `notificaciones`, `auditoria`, `equivalencias`. Each exposes `router` (APIRouter with prefix `/api/v1/...`) and keeps business rules in `service.py`. Routers never touch SQLAlchemy directly.
- Dependencies: `get_claims` (validated token claims), `require_role("Coordinador")`, `require_role("Admin")`, `get_session` (SQLAlchemy session with `SESSION_CONTEXT` already set from claims). Never read the coordinator id from a request parameter; always from `claims.oid`.
- Errors: raise `AppError(status, type, title, detail, extra)` from `app.core.errors`. The global handler renders RFC 9457 Problem Details with `instance` = correlation id. Validation errors are 422 with the same shape. Never return raw exception text to clients.
- Concurrency: `rowversion` exposed as `ETag` header (`"<hex>"`) on single-resource GETs; writes that require it read `If-Match` and raise `412` (`type: .../precondition-failed`) with the current representation in `extra.current`.
- Idempotency: writes from the PWA carry `Idempotency-Key`. `app.core.idempotency.idempotent(session, claims, key, request_hash)` returns a stored response or records the new one. Different payload with the same key is `422`.
- Audit: every write service calls `auditoria.record(session, claims, accion, entidad, entidad_id, detalle)` inside the same transaction. Every document download records too.
- Time: `app.core.clock.utcnow()` returns aware UTC. Columns `*_utc` are `DATETIME2(3)`. Presentation timezone is the client's responsibility.
- Logging: `structlog` JSON to stdout, bound with `correlation_id`, `user_oid` (hashed), `route`. Forbidden in logs: names, phones, emails, file contents, tokens, request bodies.
- Config: `app.core.config.Settings` (pydantic-settings). Read settings only through dependency injection or `get_settings()`. Startup validation refuses `AUTH_MODE=dev`, `SCAN_MODE=none`, `STORAGE_MODE=azurite`, `DB_AUTH=sql` when `ENVIRONMENT=production`.
- Storage: `app.core.storage.BlobStore` wraps `azure-storage-blob` with two containers. Only the Blob API, never the Data Lake SDK, so local and Azure behave the same.
- Tests: `pytest`. Unit tests in `tests/unit` must not need the DB. Integration tests in `tests/integration` are marked `@pytest.mark.integration` and use the live compose stack (`DB_HOST`, Azurite). Fixtures in `tests/conftest.py` mint tokens from the dev IdP for `coord_a`, `coord_b`, `admin`.
- Style: `ruff` (line length 100), `mypy --strict` on `app`. Type everything public.

## Frontend

- TypeScript strict, React 18, Vite, React Router, TanStack Query, Zod for runtime validation at the API boundary.
- `packages/auth` exports `AuthProvider` (interface: `getToken(): Promise<string>`, `account`, `login()`, `logout()`) and `createAuthProvider(config)` choosing `msal` or `dev` from `VITE_AUTH_MODE`.
- `packages/api-client` exports a typed client generated from `docs/openapi.json` (`openapi-typescript`) and `createApi(auth)` adding `Authorization`, `Idempotency-Key`, `If-Match`, and `X-Correlation-Id`. Problem Details are parsed into `ApiError`.
- All API paths are relative (`/api/v1/...`). Vite dev server proxies `/api` and `/dev-idp`. No absolute backend URLs in code.
- UI text in Spanish (the users' language). Code, identifiers, and comments in English.
- Visual language: tokens and shared components live in `packages/ui` and follow `docs/ux/DESIGN_SYSTEM.md`. No inline colours or sizes; codes from the API are shown through the label maps or the catalogs.
- Tests: `vitest` for units, Playwright in `e2e/` for workflows. Playwright tests sign in through the dev IdP user picker.
- Style: `eslint` (typescript-eslint recommended), `prettier`. Scripts per package: `dev`, `build`, `lint`, `typecheck`, `test`.

## API conventions

- Prefix `/api/v1`. Resource nouns in Spanish as in the TDD: `/sitios`, `/subidas`, `/archivos`, `/admin/cargas`, `/admin/equivalencias`, `/admin/auditoria`.
- List endpoints: cursor pagination (`?cursor=&limit=`), response `{ items, next_cursor }`.
- Delta sync: `GET /api/v1/sitios?desde=<rowversion hex>` returns `{ items, removed_ids, max_rowversion }`.
- Problem Details types: `https://pipeline.tiendas3b/problems/<slug>`.
- Headers: `ETag`, `If-Match`, `Idempotency-Key`, `X-Correlation-Id` (echoed).

## Git

- Branch `implementation` for this build. Conventional commit subjects (`feat:`, `fix:`, `test:`, `docs:`, `infra:`). Commit after each milestone with tests passing.
- Never commit `.env`, keys, node_modules, or generated blobs.
