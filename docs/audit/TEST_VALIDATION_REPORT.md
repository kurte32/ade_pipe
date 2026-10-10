# Test and validation report

What was executed during the audit, with results, the browser workflows verified, and the areas left
untested. All runs were against the live local stack (SQL Server 2022, Azurite, local OIDC issuer)
unless noted.

## Automated suites (re-run during the audit)

| Suite | Command | Result |
|---|---|---|
| Backend unit + integration | `pytest -q` in the api container | 125 passed |
| Backend, reversed collection order | reversed node-id order | 124 passed, 1 failed — `test_reload_updates_without_touching_progress` only (exposes C4) |
| Backend coverage | `pytest --cov=app` | 86% (3018 statements, 409 missed); zero coverage on `cli.py`, all five `jobs/*` entry points, partial on Azure/Entra/Defender paths (C8) |
| Frontend unit (vitest) | `pnpm -r test` | 20 passed (auth 4, api-client 3, web-admin 7, pwa 6) |
| End-to-end (Playwright) | `playwright test --list` + run | 14 tests in 6 files, pass; Vite servers confirmed up |
| Bicep | `bash infra/bicep/validate.sh` | 13 modules + 3 parameter files build and lint (compile-only) |
| Dependency audit | `pnpm audit --audit-level high`, `pip-audit` | no known vulnerabilities |

The headline counts in the delivery report (125 / 20 / 14) are all accurate, and the backend and
frontend tests are substantive: the RLS, ledger, and optimistic-concurrency tests would fail if their
controls were removed. The caveats are C4 (one test passes only in definition order), C6 (several list
assertions will break as the table grows past ~114 rows), C7 (no e2e teardown, the dev DB grows every
run), C8 (production-only paths barely covered), and C10 (no JWT algorithm-confusion test).

## Defect reproductions run during the audit

| Finding | Reproduction | Observed |
|---|---|---|
| B-01 (Critical) | 10 concurrent transitions, one shared ETag, on two different sites | `{201:10}` both times (expected `{201:1, 412:9}`); 10–12 duplicate rows in the audit ledger |
| B-02 | 6 concurrent same-key `PUT …/contacto` | `{200:1, 500:5}`; one applied, five PK-violation 500s |
| B-03 | `GET …/delta?conocidos=<2500 ids>` | HTTP 500; 3 ids → 200 |
| B-04 | 100k-row xlsx (2.92 MB) through the real parser | rejected after 43.79 s, 72.9 MB peak — limit checked after full parse |
| B-05 | 12 MB body for a 4 MB part | 422, but the whole 12 MB was received first |
| D-01 (High) | `git ls-files --error-unmatch .env.example` | not tracked |
| E-1 (High) | stop API, save in PWA, restart API, Sincronizar ahora | op stuck `estado="error"`; only per-site Reintentar drained it |
| A1 | read `_production_guard` | validates issuer, not JWKS URL |
| A5 | PUT with forged XFF + correlation id | exact values written to the immutable audit ledger |
| RLS (control, held) | app login, no session context | 0 rows on all 7 protected tables |

## Browser workflows verified in real Chrome (Claude-in-Chrome)

The Chrome extension was available for this audit (it was not during the original build, where the
browser evidence was Playwright emulation). What real Chrome exercised, with no JavaScript console
errors on any screen:
- **Admin web:** dashboard tiles; the Sitios list with cursor pagination (“Cargar más” → `…&cursor=NTA`
  → 200); a site detail page (data, contact, visit, files, history); the admin action buttons present
  and the Devolver button correctly disabled on a first-status site.
- **Coordinator PWA:** dev sign-in persisted; Mis sitios list and filter; the site capture form with
  the missing-document requirements listed and the advance button correctly disabled until met; the
  offline queue persisting across a dev-server restart; and the per-site Reintentar recovery draining a
  queued change end to end (the contact write round-tripped with its new ETag).
- **Offline reliability (E-1):** reproduced the transient-5xx wedge and its manual recovery, as above.

What real Chrome did **not** exercise, and why:
- A completed admin **return** (Devolver): the sampled site was at the first status, where the button is
  correctly disabled. The full return flow is covered by the Playwright `admin.sitios` and `pwa.flow`
  specs and by the backend `test_transiciones` suite.
- A real **upload** through the browser: not performed in Chrome. Resumable PDF upload and photo upload
  are covered by `pwa.flow.spec.ts` and by the backend `test_archivos` suite.

## Untested / not verifiable

- Anything requiring Azure: Entra sign-in and managed-identity DB auth, Graph/Teams delivery, Defender
  upload scanning, Front Door/WAF, Private Link, Key Vault reference resolution, and the whole deploy
  pipeline beyond static Bicep/workflow inspection. The deploy-path defects (D-02 to D-06) are by
  inspection; they could not be observed failing in a real subscription.
- B-06 (job batch rollback after an irreversible blob delete) needs Defender scan mode or an injected
  mid-batch failure to reproduce; it is code-evidenced only.
- Frontend (vitest) coverage was not measured numerically; the sync-engine spec was read in full.
