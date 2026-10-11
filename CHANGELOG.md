# Changelog · Pipeline de Posibles Tiendas

All notable changes, newest first. Dates are the commit dates. Nothing is tagged yet; releases
are tagged `release-x.y.z` on `main` (the deploy workflow matches `release-*`; see
`docs/RELEASE_PROCESS.md`).

## Unreleased · branch `ux-redesign` (from `prod-readiness`)

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
  without recording a download in the audit log.
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
