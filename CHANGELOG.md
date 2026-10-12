# Changelog · Pipeline de Posibles Tiendas

All notable changes, newest first. Dates are the commit dates. Nothing is tagged yet; releases
are tagged `release-x.y.z` on `main` (the deploy workflow matches `release-*`; see
`docs/RELEASE_PROCESS.md`).

## Unreleased · branch `ux-redesign` (from `prod-readiness`)

### Audit remediation (11 October 2026, `docs/audit/ENGINEERING_AUDIT_2026-10-11.md`)
Fixed, with regression tests, everything the audit rated P1 and P2 that does not need Azure:
- Ownership: a bulk reload that changes a site's coordinator moves contact, visit, files, open
  uploads and pending notices (one helper shared with admin `reasignar`); reassignment to an
  unknown oid is refused; discard proposals on terminal sites are refused.
- Concurrency: file publish/retire/purge lock and bump the site (other devices get the change);
  one `vigente` copy per document type (filtered unique index); the lote is locked on confirm;
  the outbox job claims rows and commits per row; `alembic check` is clean and runs in CI.
  SQLAlchemy's `with_for_update()` renders nothing on SQL Server, so every lock is an explicit
  `UPDLOCK` hint, verified by an HTTP burst test.
- Identity: the RLS session context uses the role the route is for; Admin is bound to the admin
  SPA client id (`AUTH_ADMIN_AZP`); the deployment guard applies to every environment but `local`,
  which is the only one that trusts the SQL certificate, serves docs or runs `e2e-cleanup`; the
  image defaults to `ENVIRONMENT=production`; SQL parameters and Graph URLs never reach logs.
- PWA: the local store belongs to one account and is cleared on an account change; every request
  times out after 30 s; a site reassigned away takes its queued changes with it (and says so);
  photo uploads read the live session after a replay; transient failures back off and never
  become terminal; a Web Lock serialises tabs; MSAL errors map to offline or sign-in.
- Admin: server-side queues (`en_revision_admin`, `devuelto`), the load review reads every page,
  a 412 reloads the site, config errors render a message.
- API: captures honour `If-Match` when sent; identical reloads keep the site's ETag; chunked
  overflows answer 413 Problem Details; site ids are bounded; CHECK constraints and the missing FK.
- Hardening round two: Front Door origin validation in the API (`FRONT_DOOR_ID`, required in
  production); per-user rate limits per route family (429 with Retry-After); `/healthz/deps`
  for administrators; `duration_ms`, entity ids, `revision` and `job_name` in logs; purge
  distinguishes a retention block (403/409) from other failures; outbox outcomes audited; multi-
  range and unknown-unit `Range` headers ignored instead of 416; the pooled-connection RLS test
  asserts one connection; four Azure Monitor alert rules in Bicep; CI service images and the
  compose stack pinned to SQL Server 2022 CU27 and Azurite 3.35.0; backend coverage gate (80 %).
- Backlog sweep: oversized workbooks refused from the sheet dimension tag (154 ms for 100k rows);
  `/readyz` reports the applied schema revision versus the code's head; every business timestamp
  is `datetime2(3)` (migration `e5f6a7b8c9d0`); load values are stored as the file has them
  (formula neutralisation is for exports); admin sites table as cards on phones; "Últimas cargas"
  rows tidy at phone width; audit actions explained in a tooltip and in the filter list; the
  design documents reconciled with the code (health paths, log field, immutability, threshold).
- Authenticated OWASP ZAP active scan of the whole API contract: 0 failures, 0 warnings over 120 URLs.
- `e2e/tools/net-timing.mjs`: time to the site list on emulated 4G and 3G (2.5 s / 1.7 s warm on
  slow 4G); Lighthouse on the built PWA: 92 / 100 / 100 / 82.
- Database outages answer 503 `service-unavailable` with `Retry-After` instead of 500; browsing-
  context isolation headers (COOP, CORP, X-Frame-Options) on both Static Web Apps. Evidence runs:
  Trivy on the production image (0 high/critical), OWASP ZAP baseline on the built PWA and the API
  (0 failures), backup/restore drill with ledger verification and RLS on the copy, database outage
  simulation with self-recovery, list latency p95 200 ms (`docs/RELEASE_READINESS.md` §2).
- `make e2e-image` (also in CI): the whole Playwright suite through the production image (no
  development dependencies, non-root, pinned base digests): 18 passed. `docs/RELEASE_READINESS.md`
  states the evidence and the first-deployment checklist.
- `make e2e-preview` (also in CI): the coordinator sign-in, accessibility and flow specs run
  against the production-built PWA with its service worker, served by `vite preview` under the
  Static Web App's Content-Security-Policy. It caught that hash-wasm needs `'wasm-unsafe-eval'`
  in `script-src`, which would have broken every upload in Azure (fixed).
- Round three: streaming SHA-256 (hash-wasm, 4 MiB slices) so a 150 MB PDF is never held in
  memory on the phone; "Volver a descargar" on Mis sitios rebuilds the cache keeping queued changes;
  axe WCAG 2 A/AA scans in both accessibility e2e specs; the `escaneando` transition is audited;
  runbooks RB-10 to RB-15 written and RB-03/06/07 corrected to match the code and the alerts.
- Infrastructure and pipeline (static): admin SPA on its own Front Door host; dev SPA→API via
  CORS and `VITE_API_BASE_URL`; SQL firewall and NSG rules for dev; control-plane digest
  promotion; diagnostics for Front Door, Key Vault and storage; pinned base images; drift and
  smoke-test parameters; prod after test; release tags promote the `main` digest; gitleaks allowlist.
- Root `README.md` rewritten as the entry point: what the system does, architecture at a glance,
  stack, quick start with the local URLs, every command, the quality gates and their last results,
  environments, the deployment flow, repository map, documentation by role, conventions and what is
  still open. `architecture/README.md` no longer says that no code exists.
- CI: the integration fixtures seed the ten dev equivalences themselves (`dev_equivalencias`), so
  `test_reasignar_moves_pending_notifications` no longer depends on `make db-seed` or on test order
  (it failed on the GitHub runner, which only initialises and migrates the database); the deploy
  smoke test reads asset paths with `while read` (shellcheck SC2013 made actionlint fail on the
  runner, where shellcheck is installed). Six stale documentation lines corrected (API docs served
  only in `local`, 14 Bicep modules, current test counts, branch convention, restore drill status,
  `/readyz` schema fields).

### Changed
- Both apps redesigned to the Tiendas 3B brand with a shared design system in `packages/ui`
  (tokens, `AppBar`, `PageHeader`, `Alert`, `Field`, `Modal` with focus trap, `StageIndicator`,
  `EmptyState`, `Icon`, `BrandMark`, label maps). Montserrat self-hosted (latin subset).
- Coordinator PWA: attention group for returned sites and blocked changes, next action per site,
  status chips, "Siguiente paso" checklist, captured data as summaries with Editar, one sync chip,
  per-field validation, map and phone links, keyboard-reachable file inputs, page titles.
- Admin: landing page with decision queues and a pipeline funnel, load preview with steps and a
  single primary action (confirm saves pending decisions first), labelled states and results,
  cancel behind a confirmation, immediate filters and coordinator names in the sites table,
  translated history, equivalences without raw GUIDs, audit log with user names and known-value
  filters plus an any-account oid option.
- e2e: two assertions updated to labelled text; new `admin.a11y` and `pwa.a11y` specs;
  `e2e/tools/screenshots.mjs` screenshot tool.
- Docs: `docs/ux/` (audit, design system, validation with before/after screenshots).

### Fixed
- Coordinator PWA: "Salir" asks for confirmation when captures are queued, in flight or blocked
  ("Sincronizar primero" / "Salir y borrar"); it still signs out directly when the phone is up to
  date. New e2e `pwa.salir.spec.ts`.
- API: `HEAD /archivos/{id}` is now routed (it answered 405) and returns the download headers
  without recording a download in the audit log. The download is now recorded after the `Range`
  check, so a 416 response is no longer audited as a download either.
- `Modal`: the mount effect no longer depends on `onClose`, so a parent re-render (the sync chip
  updating behind the sign-out dialog) no longer moves focus back to the close button.
- Backend tests: `test_concurrency.py` carries the `integration` marker, so `make test-unit` runs
  without the stack.

## Branch `prod-readiness` · 2026-10-10 to 2026-10-11 (not merged)

Phases 1 and 2 of `docs/audit/PRODUCTION_READINESS_PLAN.md`: code findings closed and the deploy
pipeline corrected (statically validated, never run against Azure).

### Fixed
- B-02 idempotency claims the key before the write so replays get the stored response.
- B-04 bulk load stops parsing at the row limit; B-05 request bodies bounded before reading;
  B-06 per-upload transactions and idempotent promotion reruns; B-08 explicit check for the
  planned action.
- A4/A6 loopback-only local ports, no exception names from `/readyz`; A5/D-12 client-controlled
  headers kept out of the ledger; A7 crafted emails cannot escape the Graph `/users/` path.
- R24 no false 412 when advancing while the previous save is in flight (PWA).
- E-2 to E-5 clearer sync states and admin affordances.
- D-03 migrate before traffic moves with automatic rollback; D-04/D-13 one image digest and one
  SPA build promoted; D-06/D-09/D-14 deploys gated on CI, e2e in CI, every action pinned;
  D-07 fail-closed dev ingress and a no-open-CIDR policy check; workflows linted with actionlint.
- CI first GitHub run fixed (pnpm 12 build approvals, ODBC keyring, shellcheck).

### Changed
- Backend suite runs order-independent under `pytest-randomly` (C4, C5); Graph adapters tested
  without a tenant; outbox keeps no raw error text (C8, C9); e2e uses a per-run site pool and
  cleans up from Playwright itself (C7).
- Docs describe the corrected pipeline, runtime SPA config and new settings.

## `main` · 2026-10-10 (PR #1, branch `implementation`)

### Added
- Foundations: FastAPI modular monolith (identity, sitios, transiciones, cargas, archivos,
  notificaciones, auditoria, equivalencias, jobs), Alembic baseline with RLS, ledger tables and
  grants, local stack (SQL Server 2022, Azurite, dev OIDC issuer, scheduler).
- Coordinator PWA with offline queue, sync engine, resumable uploads and screens; admin web
  (resumen, sitios, cargas, equivalencias, auditoría); 14 Playwright flows; package unit tests.
- Bicep templates, GitHub Actions workflows, Azure and environment docs.
- Independent adversarial audit (`docs/audit/`) and first remediation: B-01 optimistic
  concurrency enforced at the database, D-01 `.env.example` tracked, E-1 transient 5xx retried
  by the sync engine, A1/A2 JWKS host validated and unknown roles dropped, B-03 delta known-id
  list chunked, deploy-path corrections D-02/D-05/D-08.

## 2026-10-10 · planning

- Architecture set (`architecture/`: AS_IS, TO_BE, AZURE_DESIGN, SECURITY, ten ADRs,
  IMPLEMENTATION_PLAN, RISK_REGISTER, PRODUCTION_READINESS), the design review
  `Propuesta_mejoras_TDD_v0.1.md` and the source TDD.
