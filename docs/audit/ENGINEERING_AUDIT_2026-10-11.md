# Comprehensive engineering audit · Pipeline de Posibles Tiendas

Date: 11 October 2026 · Audited commit: `69f5b31` on branch `ux-redesign` (28 commits ahead of `main` and `origin/main`, 5 ahead of `prod-readiness`; working tree clean) · **Audience:** engineering lead, architect, release manager · **Status of this file:** written by the audit session with no code change; committed afterwards together with the remediation (see §L).

Method: one lead auditor plus four independent read-only auditors (identity and tenancy; data integrity and concurrency; frontend and offline sync; tests, CI and infrastructure), each told to work from code and running processes and to treat `docs/`, `docs/audit/` and `architecture/` as hypotheses. Every finding below was either reproduced against the local compose stack, read in the exact code path, or is marked *plausible*. The requirements come from `TDD_Pipeline_Tiendas_v0.1.pdf` itself (read in full), not from the repository's restatements.

**Disclosure.** The last five commits on this branch (the UX redesign, the documentation set and the two follow-up fixes) and most of `docs/` were produced by the same assistant session that ran this audit. The four auditors were started with fresh context for that reason, and two of the findings below (`LINT-1`, `DOC-1`) are defects introduced by that work.

**Side effects on the local stack** (no repository change; the ledger tables are append-only so audit rows stay): the identity auditor wrote a contact on seeded site 5 and left audit row 10628; the data auditor created sites with `origen_id` 987100–987109 (region `DATAUDIT`, ids 2250 and 2253–2261) and left site 2253 in the broken state of `DAT-1`; the frontend auditor uploaded one photo to site 71 and accidentally ran the full Playwright suite once (its `globalSetup` cleaned and re-seeded the e2e pool). Run `make reset && make up && make db-seed` before relying on local data again.

---

## A. Executive summary

**Overall engineering quality: good for code that is two days old (first code commit 2026-10-10; the TDD is dated 9 October), with a solid core and an untested edge.** The controls that matter most were re-verified under hostile probing and held: token validation (algorithm pinned, issuer, audience, tenant, `azp`, roles, expiry with 30 s leeway), row-level security with filter and block predicates on all seven owner-scoped tables, pooled connections that cannot leak a caller's identity, append-only ledgers that reject `UPDATE`/`DELETE` at the engine, optimistic concurrency that produced exactly one winner in 8- and 12-way concurrent bursts, an idempotency store that returned one audit row for 8 identical concurrent requests, correct `Content-Disposition` escaping, bounded outbox retries, and Problem Details bodies that leak nothing. Mutation testing caught nine of ten injected faults. Dependency audits of both stacks are clean. CI runs the integration suite against real SQL Server and runs Playwright.

**Most significant risks, in order:**

1. **Bulk reload reassignment corrupts site ownership (`DAT-1`, P1, reproduced).** Approving a `USUARIO` change on a `sitio_prospectado` row moves only the `sitio` row; the contact, visit, files and upload sessions keep the old `coordinador_oid`. Under RLS the new coordinator sees no contact and their first save fails with a 500 (duplicate primary key). This is the normal path the admin UI advertises ("Al aprobar se reasigna el sitio").
2. **Account switch on one phone inherits the previous user's data and queue (`FE-1`, P1, reproduced).** The IndexedDB store is not keyed by user. After a session expiry, signing in as another coordinator shows the first user's contact data, sends the first user's queued writes under the second identity (they fail with 404 and block), and inherits the first user's delta cursor so the second user sees zero sites until an explicit sign-out. TDD §5.4 requires the cache to be deleted on sign-out or expiry.
3. **The Azure deploy topology cannot work as written (`INF-1`, `INF-2`, `INF-3`, P1, static analysis).** The admin SPA behind Front Door `/admin/*` is built with base `/` and Front Door forwards the prefix unchanged; the dev environment has no path from the SPA host to the API and no network path from Container Apps to the public SQL endpoint; test/prod digest verification queries a private-endpoint registry from a GitHub-hosted runner. Nothing has ever been deployed, so none of this has been seen fail, but each will.
4. **A future `alembic revision --autogenerate` would drop `sitio.rowversion` (`CI-1`, P2, reproduced).** `alembic check` already fails for this reason and is not in CI. The column is the basis of ETag concurrency control.
5. **Several write paths bypass the site's version check (`DAT-2`, `DAT-3`, `DAT-11`/`FE-5`, P2, reproduced).** Deleting a document while the site advances can leave `recepcion_documentos` with a required document missing; concurrent uploads of the same document type leave several `vigente` copies with the same version; publishing or retiring a file never touches the site, so other devices never receive the change through the delta.
6. **CI is red at this commit (`LINT-1`, P2).** `make lint` fails on one over-long line introduced in commit `300198d`.

**Test reliability and confidence.** 153 backend tests (90 unit-marked, 63 integration), 28 frontend unit tests, 18 Playwright tests, all passing at this commit on a clean stack. Mutation probes show the transition rules, concurrency control, idempotency, PDF limits, Range handling and download audit are genuinely pinned. Gaps with real risk: the phone requirement for Dueño Localizado is not pinned (mutation survived); no test covers account switching, request timeouts, the photo-upload replay, orphaned operations, outbox concurrency, the purge job's retention arithmetic, logging redaction, MSAL, or any production-built bundle. One e2e assertion passes when the feature is broken (`TST-1`).

**Readiness.** Not production-ready, and not yet deployable to the test environment either. The blocking items split into (a) code defects fixable in days (`DAT-1`, `FE-1`, `DAT-4`, `CI-1`, `LINT-1`), (b) the deploy topology decisions (`INF-1..3`, which overlap backlog `ADMIN-BASE`), and (c) the external prerequisites already listed in `docs/IMPROVEMENT_BACKLOG.md` §1.

---

## B. Findings by severity

Confidence: **confirmed** = reproduced on the stack or read in the exact code path; **plausible** = mechanism read in code but not exercised (usually because it needs Azure or a real tenant). Ids keep the auditor prefix; items that duplicate an open backlog row cite it.

### P1 — High

| Id | Title | Confidence | Where |
|---|---|---|---|
| DAT-1 | Bulk-load reassignment strands contact, visit, files and upload sessions on the old coordinator | confirmed | `backend/app/modules/cargas/service.py:364-383` |
| FE-1 | Signing in as another account without "Salir" inherits the previous user's data, queued writes and delta cursor | confirmed | `apps/pwa-coordinador/src/db/schema.ts:57`, `App.tsx`, `sync/engine.ts:369` |
| INF-1 | Admin SPA cannot load behind Front Door `/admin/*` in test and prod (backlog `ADMIN-BASE`) | confirmed (static) | `infra/bicep/modules/frontdoor.bicep:147-151`, `apps/web-admin/vite.config.ts:13`, `.github/workflows/build-deploy.yml:125-131` |
| INF-2 | The dev environment cannot work as deployed: SPA has no route to the API; Container Apps have no network path to the public SQL endpoint | confirmed (SPA path) / plausible (SQL) | `infra/bicep/modules/staticwebapps.bicep`, `sql.bicep:39`, `network.bicep` NSG, `packages/api-client/src/client.ts:46` |
| INF-3 | Test/prod digest verification runs a registry data-plane call against a private-endpoint ACR from a GitHub-hosted runner | plausible | `.github/workflows/deploy-environment.yml:56-63`, `infra/bicep/modules/acr.bicep:28` |

### P2 — Medium

| Id | Title | Confidence | Where |
|---|---|---|---|
| CI-1 / DAT-8 | `alembic check` always fails; autogenerate would emit `drop_column('sitio','rowversion')`; no drift gate in CI | confirmed | `backend/app/models.py:153-159`, `backend/migrations/env.py:22-27` |
| LINT-1 | `make lint` (the CI lint step) fails at this commit: ruff E501 on `archivos/router.py:151`; mypy and eslint never reached | confirmed | `backend/app/modules/archivos/router.py:151` (commit `300198d`) |
| DAT-2 | Deleting a document while the site advances leaves `recepcion_documentos` without a required document | confirmed (race reproduced first try) | `archivos/service.py:407-438`, `transiciones/service.py:249` |
| DAT-3 | Concurrent uploads of one document type leave several `vigente` copies with the same version | confirmed | `archivos/service.py:295-302, 331-354`; no filtered unique index |
| DAT-4 | `reasignar` accepts any UUID or an inactive coordinator; `usuario_codigo` left stale, site invisible to everyone | confirmed | `transiciones/service.py:405-412` |
| DAT-5 | `reasignar` leaves pending notifications addressed to the old coordinator, who receives the admin's comment and a dead link (backlog `REASIGNAR-OUTBOX`) | confirmed | `transiciones/service.py:416`, `notificaciones/service.py:195` |
| DAT-6 | A coordinator can propose discard on an already `descartado` site; it then sticks in admin review and only reassignment clears it | confirmed | `transiciones/service.py:225-236` |
| DAT-7 | Outbox job sends twice when two runs overlap (no row claim, whole batch in one transaction) | confirmed with slowed sender | `backend/app/jobs/outbox.py:39-52, 101-132`; job timeout 300 s, schedule 1 min |
| DAT-11 / FE-5 | Publishing, retiring or purging a file never touches the site; the delta never delivers document or photo changes to other devices, so the PWA's requirements checklist goes stale | confirmed | `archivos/service.py:315-368` (no `_touch`), `sitios/service.py:446-451` |
| FE-2 | Queued ops for a site that was reassigned away (or returns 404) are orphaned: blocked forever, invisible, only cleared by "Salir y borrar" | confirmed | `sync/engine.ts:358-360, 380`, `pages/SitioDetalle.tsx:66-77` |
| FE-3 | No request timeout: one hung fetch freezes all syncing (manual button disabled, timer and online event coalesce into the stuck promise) | confirmed (65 s hold) | `packages/api-client/src/client.ts:72, 100`; engine comments claim otherwise |
| FE-4 | Photo-upload replay trusts the replayed `POST /subidas` body; a lost `completar` response blocks the op permanently; after 72 h the only exit deletes the photo | confirmed | `sync/engine.ts:192-217`, `backend/app/core/idempotency.py:69-71` |
| FE-6 | Non-interaction MSAL errors become terminal op errors; the PWA CSP has no `frame-src` for MSAL's silent iframe | plausible | `packages/auth/src/msal.ts:242-246`, `apps/pwa-coordinador/public/staticwebapp.config.json:14` |
| FE-7 | Admin 412 dialog says "close to reload" but closing never refetches; the dialog loops on the same stale ETag | confirmed (code) | `apps/web-admin/src/pages/SitioDetail.tsx:352-376` |
| FE-8 | Load review fetches only the first 500 rows; warnings beyond that are undecidable and "Confirmar" is enabled only to fail with 422 (loads allow 5000 rows) | confirmed (code) | `apps/web-admin/src/pages/CargaDetail.tsx:27, 50, 67, 94` |
| FE-9 | Landing-page queues are computed from the first 200 sites by id; newly loaded sites (the ones sent to review) are the ones dropped | confirmed (code) | `apps/web-admin/src/pages/Resumen.tsx:20-30` |
| IDN-2 | Deployed dev and test run with `ENVIRONMENT='test'`: production guard off, `TrustServerCertificate=yes` to Azure SQL, API docs public, `e2e-cleanup` allowed; image default is `local` | confirmed (config) | `infra/bicep/params/dev.bicepparam:39`, `test.bicepparam:35`, `backend/app/core/config.py:18, 99-100`, `core/db.py:31` |
| CI-2 | Nightly drift check can never pass: what-if omits `trafficRevision` and the dev CIDR variable, so a permanent `Modify` shows | confirmed (static) | `.github/workflows/drift.yml:45-49` vs `deploy-environment.yml:83-87` |
| CI-3 | Documented fail-closed dev ingress fallback never happens: GitHub sets the variable to `""`, rendering `ipAddressRange: ''` | confirmed | `deploy-environment.yml:36`, `dev.bicepparam:12` |
| CI-4 | Post-deploy smoke test accepts any 401; all three param files carry the all-zero tenant; guard does not check `TEAMS_APP_ID` with `NOTIFY_MODE=graph` | confirmed | `deploy-environment.yml:185-198`, `infra/bicep/params/*.bicepparam:10-17`, `core/config.py:97-125` |
| TST-1 | e2e PDF download assertion passes when the download never happens (`.catch(() => null)` then `ev === null ||`) | confirmed | `e2e/tests/pwa.flow.spec.ts` (PDF test) |
| TST-2 | Production-guard tests break eight settings at once; removing any single check still passes; no positive case | confirmed | `backend/tests/unit/test_security.py:116-127, 202-220` |
| TST-5 | Phone requirement for Dueño Localizado is not pinned: mutation removing it survived `test_rules` and `test_transiciones` | confirmed (mutation) | `backend/app/modules/transiciones/rules.py:76` |
| INF-4 | Only SQL has diagnostic settings; Front Door/WAF (Prevention mode, silent blocks), Key Vault and both storage accounts log nothing | confirmed (static) | `infra/bicep/modules/*.bicep` (`diagnosticSettings` only in `sql.bicep`) |

### P3 — Low

| Id | Title | Confidence | Where |
|---|---|---|---|
| IDN-1 | A token carrying both app roles gets Admin-scoped RLS on coordinator write routes (route gate is set-intersection, context uses `primary_role`) | confirmed | `backend/app/core/security.py:38-43, 129`, `core/db.py:114` |
| IDN-3 | SQLAlchemy exception text logs bound parameters (owner names, phones) on DB errors | confirmed mechanism | `core/db.py:52-59` (`hide_parameters` not set), `core/logging.py:239-245` |
| IDN-4 | `httpx` INFO logs print Graph URLs with coordinator emails and raw oids outside structlog | confirmed | `core/logging.py:58-59`, `equivalencias/directory.py:57-58`, `notificaciones/graph.py:52` |
| IDN-5 | Roles are not bound to the client (`azp`): Admin works from the PWA client id, bypassing policies scoped to the admin SPA registration | confirmed | `core/security.py:83-85` |
| IDN-6 | The app login can set `rol='Admin'` in session context itself; RLS is only as strong as the static-SQL discipline | confirmed (design) | `core/db.py:99-101`, baseline predicate |
| IDN-7 | Oversized chunked uploads return 400 with a non-Problem-Details body instead of 413 | confirmed | `core/limits.py:152-171` |
| IDN-8 | No application-level or per-user rate limiting; only Front Door WAF 300/min per IP, absent in dev | confirmed | `frontdoor.bicep:60-75`, `dev.bicepparam:8` |
| IDN-9 | JWKS refresh under a global lock with a 30 s timeout can stall every request when Entra is slow | plausible | `core/security.py:54-56` |
| API-1 | `GET /api/v1/sitios/99999999999999999999` returns 500 (`OverflowError` from pyodbc) instead of 404/422 | confirmed | `modules/sitios/service.py:110`; path param is unbounded `int` |
| DAT-9 | `PUT /contacto` and `PUT /visita` ignore `If-Match`; a stale sequential write wins | confirmed | `transiciones/service.py:125-208`, `router.py:65-100` |
| DAT-10 | A no-op reload still bumps every site's rowversion, invalidating every queued offline transition | confirmed | `cargas/service.py:260-271` |
| DAT-12 | Concurrent confirms of one lote return 500 (unique violation) instead of 409; nothing locks the lote | confirmed | `cargas/service.py:277-282` |
| DAT-13 | Writes without an audit row: mark-read, `escaneando` transition, upload expiry, outbox send result, purge blocked by legal hold, per-site reload changes; archive audit rows omit IP | confirmed (code) | see §D |
| DAT-14 | No CHECK constraints or filtered unique indexes; business tables use `datetime`, ledgers `datetime2(3)`; `subida_sesion.tipo_documento` has no FK | confirmed | baseline migration |
| DAT-15 | Terminal status `entregado` is unreachable (backlog `ENTREGADO`) | confirmed | `models.py:39`, `rules.next_estatus` |
| DAT-16 | Multi-range and unknown-unit `Range` headers return 416 where RFC 9110 prefers 200 with the full body | confirmed | `archivos/validation.py:110-135` |
| DAT-17 | `neutralize()` prefixes `'` at load time into staging originals; TDD §8.1 asks for neutralisation on export (there is no export) | confirmed | `cargas/validation.py:94-99, 209` |
| FE-10 | A contact or visit queued before a transition hides a concurrent server change (successor map records an unconditional write as "ours") | confirmed (code) | `sync/engine.ts:155-168, 293-299` |
| FE-11 | Idempotency "in flight" 409 is classed as a blocking conflict; two tabs can block each other | plausible | `sync/engine.ts:228` |
| FE-12 | MSAL `busy` flag sticks if `loginRedirect` throws; first cached account chosen arbitrarily | plausible | `packages/auth/src/msal.ts:201, 250-254` |
| FE-13 | Missing or invalid `config.json` gives a blank page (rejection swallowed by `void main()`) | confirmed (code) | `apps/*/src/main.tsx:18-33` |
| FE-14 | Transient retries: 5 attempts on a fixed 30 s timer, then terminal `error`; a 10-minute outage needs manual retries per site | confirmed (code) | `sync/engine.ts:244-256, 325-327` |
| FE-15 | Grouped UI correctness: oldest queued contact payload shown; mark-read errors silent; "(sin conexión)" shown for 404/410; dead `web-admin/components/Modal.tsx`; equivalences silently drop cleared rows; review text always blames a load | confirmed (code) | see §D |
| TST-3 | Tests leak data and depend on order (cargas cleanup by name prefix, `test_equivalencias` without `finally`, `pickProspectado` fallback to a returned site, e2e pool sized for ~8 consumers with retries) | confirmed | `backend/tests/integration/test_cargas.py:117-121, 227`, `test_equivalencias.py:63-71`, `e2e/tests/pwa.flow.spec.ts:24` |
| TST-4 | Stale-write and pooled-RLS tests are indirect (ORM-level `StaleDataError`; no `@@SPID` assertion; ledger test accepts "does not exist") | confirmed | `test_concurrency.py:46-68`, `test_identity_and_rls.py:107-118` |
| INF-5 | Production image ships `tests/` and the `e2e-cleanup` command; base images not pinned by digest; Trivy only on CRITICAL with `ignore-unfixed` | confirmed | `backend/.dockerignore`, `Dockerfile:2,18,22`, `cli.py:94` |
| CI-5 | Smaller pipeline issues: no `pipefail` around `az … \| jq`; `inputs.image_digest` interpolated into `run:`; release tags rebuild the image instead of promoting the `main` digest; prod does not depend on test; `:latest` service images in CI; Azurite healthcheck always healthy | confirmed | `deploy-environment.yml:73-78`, `build-deploy.yml:71, 154-174`, `ci.yml`, `docker-compose.yml:29` |
| CI-6 | Full-history gitleaks flags the public Azurite key in `.env.example` (no allowlist); CI's range scan passes by luck | confirmed | `.env.example:33` |
| DOC-1 | `docs/openapi.json` is stale (lacks `HEAD /archivos/{id}`; differs beyond paths); `make openapi` was not rerun after `300198d` | confirmed | `docs/openapi.json` |

---

## C. Architecture and design gaps

1. **Ownership is denormalised and has two reassignment paths that disagree.** `coordinador_oid` is copied onto five child tables so RLS can filter them, which is sound, but the invariant "all children match the parent" is enforced only in the admin `reasignar` loop and not in the bulk-load path (`DAT-1`). There is no database-level guard and no helper shared by the two paths. Decision missing: either a single `reassign_site()` service used by every path, or RLS on child tables through a join to `sitio` (slower but one source of truth).

2. **The site's `rowversion` is the only concurrency token, but not every write to the site's aggregate bumps it.** Files, upload sessions, notifications and document deletion change what the site "is" without touching the row (`DAT-2`, `DAT-3`, `DAT-11`). The design needs a stated rule: any write that changes the site's eligibility to advance, or what a device should refresh, calls `_touch(sitio)` inside the same transaction, and reads that compete with it lock the row.

3. **One `environment` value conflates "local convenience" with "deployed non-production" (`IDN-2`).** Dev and test deploy as `test`, which turns off the production guard, certificate validation and the `e2e-cleanup` refusal. A `deployed` or `db_auth` based switch is needed; defaults should fail closed (an image started without `ENVIRONMENT` runs as `local`).

4. **The client store is a per-device singleton, not a per-user one (`FE-1`).** TDD §5.4 ("al cerrar sesión, expirar la sesión o borrado selectivo se elimina la caché local") is implemented only for the explicit "Salir". The sync engine, delta cursor and successor map need an owner oid.

5. **The Azure topology was designed on paper and has three routing assumptions nobody has run (`INF-1..3`).** Path-based routing for two SPAs, a dev environment without Front Door, and digest promotion through a private registry from hosted runners. The backlog already recommends host-based routing for the admin; dev needs either Front Door or an SWA linked backend plus a SQL private endpoint; promotion needs a control-plane check or a VNet runner.

6. **Jobs assume single-instance execution.** The outbox (`DAT-7`) and, by the same pattern, the purge and expiry jobs take no row claims. Container Apps scheduled jobs can overlap when a run exceeds its interval.

7. **Observability stops at the API.** Structured logs and correlation ids are good; nothing on Front Door, WAF, Key Vault or storage writes diagnostics (`INF-4`), and the WAF runs in Prevention mode with silent blocks on 4 MB binary parts. Application-level rate limiting is absent (`IDN-8`).

8. **Admin pages assume small data.** The landing queues (`FE-9`) and the load review (`FE-8`) truncate silently where the API itself paginates correctly. Server-side filters and counts for "needs decision" are missing from the API contract.

9. **Role model: route gate versus RLS role (`IDN-1`, `IDN-5`).** `require_role` checks membership while the session context takes the highest role; roles are not bound to the SPA client id, so the Conditional Access split between the two registrations (ADR-006) can be sidestepped by a user holding both roles.

10. **Undocumented behaviours found in code, absent from the TDD or ADRs:** `descartado` as a coordinator-proposed, admin-confirmed status; `en_revision_admin` as a review flag set by loads and proposals; the 7-day idempotency window versus 72-hour upload sessions; the `'`-prefix neutralisation at load time (`DAT-17`); the 200-site landing cap. None is wrong by itself, but each is a business rule living only in code.

Overengineering: none found that costs correctness. The successor map in the sync engine (`engine.ts:47-61`) is the most intricate piece and is tested, though `FE-10` shows its rule ("my write's new ETag supersedes the old") is one step too generous.

---

## D. Implementation defects

Details for the findings a developer will pick up first. Each has the evidence the auditor collected; reproduction steps are against `make up && make db-seed`.

**DAT-1 — Bulk reassignment strands child rows (P1).**
Evidence: loaded a CSV changing row 987101 from `ard` to `mmi`; preview `advertencia actualizar ['usuario_cambiado']`; approved; confirm 200. SQL afterwards (re-verified by the lead auditor): site 2253 `coordinador_oid …0002`, `sitio_contacto.coordinador_oid …0001`, `sitio_visita.coordinador_oid …0001`. `mmi GET /sitios/2253` → `contacto: null, visita: null`; `mmi PUT /sitios/2253/contacto` → 500 with `IntegrityError … PRIMARY KEY … duplicate key (2253)`. Root cause: the `ACCION_ACTUALIZAR` branch (`cargas/service.py:364-383`) sets `prev.coordinador_oid` only; the admin `reasignar` (`transiciones/service.py:416-419`) updates `SitioContacto`, `SitioVisita`, `SitioArchivo`, `SubidaSesion`. Fix: extract that loop into one helper and call it from both paths (and add `NotificacionOutbox` pending rows, see `DAT-5`). Regression: integration test capturing a contact, reloading with a new `USUARIO`, approving, confirming, then asserting the new coordinator reads the contact and `PUT /contacto` returns 200.

**FE-1 — Account switch inherits the previous user's store (P1).**
Evidence (Playwright scripts `multi.mjs`, `cursor.mjs`): `ard` signs in and syncs; token removed to simulate expiry; "Tu sesión expiró" → "Iniciar sesión para sincronizar" → sign in as `mmi`. Immediately: `mmi` sees `ard`'s eight site names; `ard`'s offline contact is sent as `PUT /sitios/1/contacto` with `mmi`'s token → 404 → `bloqueada`; `mmi`'s delta is `desde=0000000000004D6A&conocidos=1,6,…` → 0 items; UI shows 0 sites while the API has 17, still after reload. Root cause: single Dexie database `pipeline-coordinador` (`schema.ts:57`), cleared only by "Salir"; no oid comparison on re-login; global delta cursor. Fix: store the owner oid in `meta`; on account change with a different oid call `clearLocalData` and `queryClient.clear()` before mounting `SyncProvider` (or name the DB by oid). Regression: e2e signing in as `ard`, expiring, signing in as `mmi`, asserting `mmi`'s count equals the API and no `ard` ops remain.

**DAT-2 — Document delete versus advance race (P2).** Two threads behind a barrier: `{'delete': 204, 'advance': 201}`, final `recepcion_documentos` with `uso_de_suelo` missing. Neither `soft_delete` nor `promote` touches the site row, so the version check cannot see the conflict. Fix: `with_for_update()` on the site in `soft_delete`/`promote` or `_touch(sitio)`; re-check requirements under the lock in `avanzar`.

**DAT-3 — Duplicate `vigente` versions (P2).** Four parallel `completar` for `escritura_hipoteca`: `[(200,2),(200,3),(200,3),(200,3)]`, final rows `[(1,False),(2,True),(3,True),(3,True),(3,True)]`. Fix: filtered unique index `(sitio_id, tipo_documento) WHERE vigente=1 AND tipo='documento'` plus a site row lock before computing `max(version)+1`.

**DAT-4 — Reassign to nobody (P2).** `POST /admin/sitios/2255/reasignar {"coordinador_oid":"deadbeef-…"}` → 200; `usuario_codigo` stays `ard`, `coordinador_oid` is the unknown value; the site is invisible to every coordinator and the next load sees no change. Code: `sitio.coordinador_oid = nuevo` is executed before the `equiv is not None` check (`transiciones/service.py:410-412`). Fix: `raise unprocessable` when `equiv is None`.

**DAT-5 — Notifications do not follow reassignment (P2).** After `devolver` ("comentario confidencial DAT") then `reasignar` to `mmi`: `ard`'s `GET /notificaciones` still lists it (and `GET /sitios/2257` → 404 for `ard`); `mmi`'s list is empty. This is the business decision filed as `REASIGNAR-OUTBOX`; the auditor's evidence shows the privacy side (the admin's comment reaches someone who no longer owns the site), which argues for re-addressing or cancelling pending rows rather than leaving them.

**DAT-6 — Discard proposal on a discarded site (P2).** After admin `descartar` on 2254, coordinator `POST /transiciones {"estatus_destino":"descartado"}` → 201; `en_revision_admin` true; `devolver` and `descartar` now return 422 on that site; only `reasignar` clears it. Fix: terminal-status check before the proposal branch (`transiciones/service.py:225`).

**DAT-7 — Outbox double send (P2).** Two threads running the real `outbox.run` with a 1.5 s sender: `sends: [('replica0', 2256), ('replica1', 2256)]`, both logged `enviadas=1`. Query at `jobs/outbox.py:45` has no `UPDLOCK, READPAST`; the whole batch commits at the end, so a killed run resends everything. Fix: claim rows (`estado='enviando'`) in a short transaction, send, commit per row.

**DAT-11 / FE-5 — Files never reach other devices (P2).** After a photo publish to site 71, `delta?desde=<rowversion before>` returns `[]` while the site has one file; `promote()` has no `_touch` (re-verified: no `_touch` or `rowversion` in `archivos/service.py`). The uploading device refreshes itself through `touched`; any other device, an admin retirement, and the Defender 202 → job publish path leave the PWA's requirements checklist stale, disabling or wrongly enabling "Avanzar". Fix: `_touch(sitio)` in `promote`, `soft_delete`, purge.

**FE-2 — Orphaned operations (P2).** After an admin reassignment, the device shows `ops: [{sitioId:1, estado:'bloqueada', error:'El sitio ya no está asignado a ti o no existe.'}], sitios: []`; chip "1 requieren atención"; `/sitios/1` renders "Este sitio no está en el teléfono" with no conflict panel. The sign-out dialog added in `300198d` tells the user to resolve it from the site, which is impossible. Fix: delete `operaciones` and `fotos` for removed ids inside the `pullDelta` transaction and the 404 branch (record what was lost), or render orphans in a global panel.

**FE-3 — No request timeout (P2).** With `/sitios/delta` held unanswered: after 65 s `PUTs attempted: 0`, chip "Sincronizando…" disabled, a contact saved meanwhile never sent. `client.ts:72,100` pass only the caller's signal; nothing supplies one. Fix: default `AbortSignal.any([opts.signal, AbortSignal.timeout(30_000)])` and map the abort to `NetworkError` (today a raw `DOMException` would be classed as terminal `error` at `engine.ts:260`).

**FE-4 — Photo replay (P2).** Create with key K → `abierta, partes_recibidas: []`; part 0; `completar` → `publicado`. Replay create with K → 201 with the stale `abierta` body; part 0 → 422 "La sesión de subida está en estado 'publicada'". `resumable.ts:100-113` already handles this correctly for PDFs by reading the live session; `uploadFoto` does not. Fix: `GET /subidas/{id}` after create and branch on live state; mint a new key when the session is expired or rejected.

**IDN-1 — Dual-role token (P3).** `ard` with `roles=["Coordinador","Admin"]`: `GET /sitios/5` → 200 (404 with Coordinador only); `PUT /sitios/5/contacto` → 200; audit row 10628 records `rol=Admin, accion=contacto_capturado` on `mmi`'s site. Needs Entra to assign both roles to one person. Fix: pass the matched role into `set_session_context`, or reject dual-role tokens.

**API-1 — Integer overflow → 500 (P3).** `GET /api/v1/sitios/99999999999999999999` → 500 `internal`; log shows `OverflowError: int too big to convert` at `sitios/service.py:110`. Body leaks nothing. Fix: `Path(..., le=2**31-1)` or catch and map to 404.

**DAT-13 — Writes without audit rows (P3).** `notificaciones/service.py:244-256` (mark read), `archivos/service.py:285-292` (`escaneando`), `jobs/expire_uploads.py:29-32`, `jobs/outbox.py:121-131` (send outcome), `jobs/purge.py:262-269` (blocked by legal hold, retried daily, never recorded), `cargas/service.py:356-383` (per-site changes only as a batch total). RNF-07 says every write leaves a trace; the ones that matter most are the legal-hold block and expiry deletes.

**FE-15 details (P3).** `SitioDetalle.tsx:61-63` `ops.find` shows the oldest queued contact; `Notificaciones.tsx:17` mark-read failure silent; `FotosSection.tsx:181-201` "(sin conexión)" for 404/410; `apps/web-admin/src/components/Modal.tsx` unused; `Equivalencias.tsx:47-49` drops rows with cleared email yet reports saved; `SitioDetail.tsx:117-121` review text always says a load caused it.

**Maintainability notes (not defects).** `models.py` doc says RLS applies to "every table that…" and is accurate; `engine.ts:9,32` and `schema.ts:27` comments claim timeouts that do not exist (`FE-3`); `dev.ts:3` says the dev provider is never bundled, but it is (guarded by config); `pyproject` silences all `DeprecationWarning`s, hiding the Starlette TestClient deprecation and anything future.

---

## E. Testing assessment

**Executed at commit `69f5b31` (clean stack, before the auditors' probes):**

| Suite | Command | Result |
|---|---|---|
| Backend, full | `make test` 14:57:37–14:57:51 | 153 passed, 1 warning, exit 0 |
| Backend, markers | `pytest --collect-only -q -m integration` / `-m "not integration"` | 63 / 90 (all 63 under `tests/integration/` carry the marker) |
| Frontend unit | `pnpm -r --filter '!e2e' test` | 28 passed (auth 8, api-client 3, web-admin 7, pwa 10); `packages/ui` has none |
| Playwright | `cd e2e && pnpm exec playwright test` | 18 passed in 27.8 s (10 pwa-mobile, 8 admin-desktop) |
| Playwright, incidental second run by the frontend auditor on the shared, mutated stack | same | 15 passed, 3 failed (PDF resumable, `pwa.salir` because a probe had already saved a contact on the picked site, equivalences trace ENOENT); attributed to shared-stack contamination, not to the code |

Note on documented counts: `docs/DEVELOPER_GUIDE.md` says "58 unit + 63 integration"; the actual split is 90 non-integration + 63 integration = 153 (the 58 was stale before the UX branch). `IMPLEMENTATION_STATUS.md` says `make test` 125; that was true on 2026-10-10.

**Mutation probes** (backend copied to the scratchpad and mounted at `/mut`; the first attempt mounted over `/app` and was silently overridden by the compose bind, which made all ten faults "survive" until the import path was verified; recorded so nobody repeats it):

| # | Fault | Caught |
|---|---|---|
| M1 | `version_id_col` removed | yes (`test_concurrency`) |
| M2 | `set_session_context` no-op | yes (19 errors in RLS tests) |
| M3 | contact precondition removed | yes (2) |
| M4 | idempotency body-hash check dropped | yes (1) |
| M5 | PDF page limit ×10 | yes (2) |
| M6 | download audit never written | yes (1) |
| M7 | Range end not clamped | yes (1) |
| M8 | Range start ≥ size not 416 | yes (3) |
| M9 | devolver to same status allowed | yes (1) |
| M10 | **phone no longer required for Dueño Localizado** | **no, 19 passed** (`TST-5`) |

**Test-quality findings:** `TST-1` (download assertion accepts a timeout), `TST-2` (guard test cannot localise a removed check), `TST-3` (data leaks and order dependence), `TST-4` (indirect concurrency and RLS tests), plus: `test_cargas.py:227` reads with `limit=200` and no paging; `admin.cargas.spec.ts:8` derives ids from `Date.now()`; the e2e pool holds 10 `ard` sites for roughly 8 consumers with `retries: 1` in CI.

**No meaningful automated coverage (risk in parentheses):**
- Account switching on one device (`FE-1`, PII).
- Request timeout and stuck sync (`FE-3`, availability).
- Photo op end to end: parts, replay, blob gone, 202 (`FE-4`, data loss).
- `pullDelta` removals while ops exist; `refreshSitio` 404 branch (`FE-2`).
- Outbox: `MAX_ATTEMPTS → fallida`, backoff cap, at-least-once after a failed batch commit, overlapping runs (`DAT-7`, duplicate Teams messages).
- Purge: retention date arithmetic (`archivos/service.py:360`), behaviour against a WORM container (Azurite has none; immutability equals purge time to the day, so any drift yields 409 forever).
- Upload cancel/abandon: staging deletion, foreign user cancelling, parts after cancel, the lifecycle rule.
- Reassignment side effects beyond child rows (notifications, open sessions).
- Logging redaction: no test uses `caplog`; redaction covers top-level keys only (`IDN-3`, `IDN-4`).
- MSAL provider (127 lines, zero tests; e2e uses dev auth only); `createApi().request`; `context.tsx`; `resumable.ts`; `photos.ts`; `clearLocalData`; all of `packages/ui`.
- Config guard per rule and acceptance of a valid production config (`TST-2`, `CI-4`).
- Production-built bundles, the service worker, SWA CSP/headers: e2e runs against Vite dev servers with the service worker disabled. *(Closed on the same day: `make e2e-preview` runs the coordinator specs against the built bundle with the service worker; SWA headers still need Azure.)*
- Rate limiting (none exists), Range `If-Range`/multi-range, admin cancel/discard edge cases.
- The Entra `db_auth` branch of `db-init` (`cli.py:27-41`) and the migrate job as deployed.
- Coverage percentage: `pytest-cov` is not installed in the image; no line or branch figure exists for the backend. Vitest coverage is not configured.

**Flakiness:** none observed in the one full Playwright run on the final tree (18 passed, 27.8 s) nor in the two full runs on the preceding tree state earlier the same day. The pool design makes `--repeat-each` and parallel workers unsafe by construction (`TST-3`).

---

## F. Security and reliability

**Confirmed and verified controls** (probed, not assumed): RS256 only, `alg:none`/unknown kid/no kid → 401; wrong `aud`, `iss`, `tid`, missing `iat`, future `nbf`, garbage, double tokens → 401; `azp` allowlist; `oid` must be a UUID; roles filtered to the two known values (forged `Sistema` → 403); expiry with 30 s leeway; every route carries a `require_role` dependency (33 routes enumerated); coordinator on admin route → 403 and vice versa; no-role token → 403. `pipeline_app` with no session context reads 0 rows from all seven RLS tables; the same SPID after check-in reads `(None, None)`; a mid-request `commit()` drops the context and fails closed; `ALTER SECURITY POLICY` → 33268, `CREATE TABLE` → 262, `UPDATE auditoria` → 37359. Production guard rejects dev JWKS, dev issuer, look-alike host, empty `azp`, `Production` casing; Bicep derives issuer/JWKS from `loginEndpoint`. Correlation id is server-generated; client value sanitised to `[A-Za-z0-9_.-]`. 13 MB body → 413 before authentication. No CORS middleware (deny by default). Error bodies carry no stack, SQL or path. No tokens in 30 minutes of API logs. `.env` ignored, `.env.example` tracked with dev-only values; all workflow `uses:` pinned by SHA; storage `allowBlobPublicAccess:false`, `allowSharedKeyAccess:false`, TLS 1.2; SQL Entra-only; Key Vault RBAC with purge protection; WAF Prevention with DRS 2.1; compose binds every port to `127.0.0.1`; image runs as uid 10001. `pnpm audit` and `pip-audit` (286 pinned packages): no known vulnerabilities.

**Confirmed issues (security or reliability):**
- `IDN-2` deployed non-prod accepts any SQL server certificate and runs with the guard off.
- `IDN-3`, `IDN-4` personal data can reach logs (SQL parameters on DB errors; httpx request lines with emails and oids).
- `IDN-1`, `IDN-5` role mapping and client binding gaps (require Entra to grant both roles, or an Admin to use the PWA client).
- `DAT-5` an admin's return comment is delivered to a coordinator who no longer owns the site.
- `FE-1` cross-user data on a shared device after expiry.
- `DAT-7` duplicate notifications under overlapping job runs.
- `FE-3` one hung request stops all synchronisation until the browser gives up.
- `INF-4` no WAF, Key Vault or storage diagnostics; silent WAF blocks.
- `INF-5` tests and the destructive `e2e-cleanup` command ship in the image; in dev/test nothing blocks it.
- `CI-5` `inputs.image_digest` interpolated into a shell `run:` (script injection by anyone allowed to dispatch); release tags rebuild rather than promote the digest that dev ran.

**Potential risks needing verification in Azure or a tenant:** `INF-3` (private ACR data plane from hosted runners), `INF-2` SQL path, ARM's handling of `ipAddressRange: ''` (`CI-3`), WAF behaviour on 4 MB binary upload parts, Front Door Private Link approval (no workflow step), `FE-6` MSAL silent iframe under the CSP, `IDN-9` JWKS lock under load, Application Insights capturing SQL parameters, async cross-account blob copy returning `pending` (would raise in `promote`), Defender scan states, offline queue older than the 7-day idempotency window replaying contact/visit writes (combines with `DAT-9`).

**Not done:** no penetration test (HU-18), no load test, no device test on Intune-managed Android (RNF-03), no screen-reader pass.

---

## G. Requirements traceability

Source: `TDD_Pipeline_Tiendas_v0.1.pdf` §3, §15. Status vocabulary: **implemented** (code path exists and behaves as specified locally), **tested** (automated test pins it), **partial**, **missing**, **unverified** (needs Azure, a tenant or a device). Evidence names tests and findings.

| Req | Implemented | Tested | Status | Notes |
|---|---|---|---|---|
| RF-01 Entra sign-in from mobile | dev issuer yes; MSAL written | `test_security` (token negatives), `pwa.signin.spec` (dev picker) | **unverified** for MSAL | `FE-6`, `FE-12` plausible; no tenant |
| RF-02 only assigned records | yes (RLS + service filter) | `test_identity_and_rls`, M2 caught, e2e | implemented, tested | `IDN-1` dual-role exception; `DAT-1` breaks it after bulk reassignment |
| RF-03 one-step advance with minimum requirements | yes | `test_rules`, `test_transiciones`, M3/M9 caught | partial | phone requirement unpinned (`TST-5`); `DAT-2` race; `DAT-6` terminal gap |
| RF-04 contact, measurements, photos, documents | yes | e2e flow, `test_archivos` | implemented, tested | `FE-4` photo replay; `FE-5` cross-device delta |
| RF-05 bulk load with preview and approval | yes | `test_cargas_*` (unit), `test_cargas` (integration), `admin.cargas.spec` | implemented, tested | `DAT-1` reassignment defect; `FE-8` >500 rows; `DAT-10`, `DAT-12` |
| RF-06 return with mandatory reason | yes | `test_transiciones`, `admin.sitios.spec` | implemented, tested | |
| RF-07 Teams notice on return | outbox + in-app yes; Graph sender written | `test_notificaciones` (log mode) | partial, **unverified** delivery | `DAT-7` duplicates; `DAT-5` wrong recipient after reassignment; `CI-4` empty `teamsAppId` |
| RF-08 resumable PDF upload, validation, OneLake | staging + "documents" container yes; OneLake path in Bicep only | `test_archivos`, `test_archivos_validation`, M5/M7/M8 caught, e2e PDF | partial, **unverified** OneLake/Defender | `TST-1` weak download assertion; `DAT-3` duplicate versions |
| RF-09 equivalences and reassignment | yes | `test_equivalencias`, `admin.equivalencias.spec`, `admin.sitios.spec` | partial | `DAT-4` reassign to unknown oid; `DAT-5` notifications; Graph directory unverified |
| RF-10 immutable log of status, loads, downloads, returns | ledger tables, INSERT-only | `test_identity_and_rls` (37359), `test_archivos` (download), M6 caught | implemented, tested | `DAT-13` some writes unaudited |
| RF-11 5-year retention, audited purge | purge job yes | unit purge tests with hand-set `purga_utc` | partial, **unverified** immutability | retention arithmetic untested; legal-hold block never audited; start event pending (TDD 7) |
| RNF-01 isolation API/service/DB, encryption, no secrets | yes locally; TLS/private endpoints in Bicep | RLS suite, secrets scan | implemented locally, **unverified** Azure | `IDN-2` certificate trust in deployed non-prod |
| RNF-02 no capture lost offline, idempotent ops | yes | `engine.test.ts` (10), e2e offline, idempotency probes | partial | `FE-1`, `FE-2`, `FE-3`, `FE-4`, `FE-14` can lose or strand captures |
| RNF-03 Intune Android, PWA browser | manifest + SW built | none | **unverified** | needs a device |
| RNF-04 retention 5 years | see RF-11 | | partial | |
| RNF-05 PDF ≤ 50 pages, ≤ 150 MB | yes | validation tests, M5 caught | implemented, tested | |
| RNF-06 UTC storage, Mexico City display | yes | `dates.test.ts`, backend UTC tests | implemented, tested | `DAT-14` `datetime` precision in business tables |
| RNF-07 every write and download audited | mostly | `test_archivos`, M6 caught | partial | `DAT-13` list |
| RNF-08 list < 3 s on 4G | single paged query | none | **unverified** | |
| HU-01 | see RF-01 | | unverified (MSAL) | token renewal without re-prompt untested |
| HU-02 | see RF-02 | | tested | |
| HU-03 preview, nothing inserted before confirm | yes | `test_cargas`, e2e | tested | |
| HU-04 decisions on doubtful rows, errors not approvable | yes | `test_cargas` | tested | `FE-8` beyond 500 rows |
| HU-05 equivalence errors and audit | yes | `test_equivalencias` | tested | |
| HU-06 detail with return comment | yes | e2e conflict scenario | tested | |
| HU-07 / HU-08 advance gates | yes | `test_rules`, e2e | tested | phone gate unpinned |
| HU-09 all documents vigente; reject bad PDFs | yes | `test_archivos`, soft-delete probe | tested | `DAT-2` race |
| HU-10 offline capture, no duplicates, pending visible | yes | e2e offline, engine tests | tested | `FE-1..4` |
| HU-11 resume interrupted upload | yes | backend resume tests, `resumable.ts` | tested (API), e2e download assertion weak (`TST-1`) | |
| HU-12 photos compressed and stored | yes | e2e photo | tested | OneLake unverified |
| HU-13 return with history and data kept | yes | `admin.sitios.spec` | tested | |
| HU-14 Teams notice, no personal data, failure does not revert | yes (log mode) | `test_notificaciones` (redaction of PII in error text) | partial | delivery unverified |
| HU-15 audit viewer with filters | yes | `admin.auditoria.spec` | tested | |
| HU-16 files in Fabric with metadata | metadata yes; Mirroring/shortcut Bicep only | none | **unverified** | |
| HU-17 purge with legal hold | job yes | unit | partial, unverified | |
| HU-18 pen test and RLS tests before production | RLS tests yes | | partial | no pen test |
| TDD §5.4 cache deleted on sign-out or expiry | sign-out only | `pwa.salir.spec` | **partial, defect** | `FE-1` |
| TDD §8.1 formula neutralisation on export | at load time instead; no export exists | unit | deviation | `DAT-17` |
| TDD §13 CI/CD with tests, static analysis, dependency and container scanning | yes | CI run 38106114922 green (6 jobs) on the last pushed commit of `prod-readiness`, not on this unpushed branch | implemented, **red at this commit** (`LINT-1`: `ci.yml` runs the same `ruff check .` as `make lint`) | deploy workflows never executed |
| TDD §14 offline: session expiry with pending queue | banner exists | none | **untested** | |
| TDD pendientes 4, 5, 7, 8, 9, 13 | provisional values seeded; privacy notice absent | | open business decisions | `IMPROVEMENT_BACKLOG.md` §6 |

**Unverified assumptions carried by the design:** Front Door appends `X-Forwarded-For` so that `hops=2` yields the client IP; Entra will issue v2 tokens with `roles`; users will never hold both app roles; Container Apps scheduled jobs do not overlap; Azure SQL read-committed snapshot does not change the race outcomes above; the OneLake write path performs at 150 MB; coordinators never share a phone.

---

## H. Prioritized remediation plan

**1. Immediate (before any further merge or deployment; each is hours):**
- Fix `LINT-1` (wrap the decorator line) so CI is green; rerun `make openapi` (`DOC-1`).
- `DAT-1`: shared `reassign_site()` helper used by `cargas.confirm` and `reasignar`, moving all five child tables; include pending outbox rows (`DAT-5`) once the business decision is taken, otherwise cancel them.
- `DAT-4`: reject reassignment to an unknown or inactive coordinator.
- `CI-1`: exclude `sitio.rowversion` in `include_object`; add `alembic check` to the CI backend job. Do this before anyone runs autogenerate.
- `FE-1`: store the owner oid; clear the store and query cache on account change.
- `FE-3`: default request timeout in the API client, mapped to a transient error.
- Reset the local stack (`make reset`) to remove the auditors' data.

**2. High priority (before the test environment deploys; days):**
- Deploy topology decision and implementation: `INF-1` (host-based admin routing, per backlog), `INF-2` (dev: Front Door or SWA linked backend, SQL private endpoint or NSG rule), `INF-3` (control-plane digest check or VNet runner). Group with `CI-2`, `CI-3`, `CI-4` since they touch the same workflow and param files.
- `IDN-2`: split "deployed non-prod" from "local"; tie `TrustServerCertificate` to `db_auth`; make `ENVIRONMENT` required; make `e2e-cleanup` allow only `local` (`INF-5`).
- Version-check integrity: `DAT-11`/`FE-5` (`_touch` on file publish/retire/purge), `DAT-2` (site lock in `soft_delete`/`promote`), `DAT-3` (filtered unique index + lock). One change set, one migration.
- `DAT-7`: row claims in the outbox job; apply the same pattern to purge and expiry.
- `FE-2`, `FE-4`: orphan handling and live-session check in the photo path.
- `DAT-6`: terminal check before discard proposal.
- Tests: `TST-5` (phone rule), `TST-1`, `TST-2`, plus the regression tests named for each item above.

**3. Medium priority (before go-live):**
- `FE-7`, `FE-8`, `FE-9` admin correctness at scale (server-side queue filters and counts; paginated review; reload on 412).
- `IDN-1`, `IDN-5` role-to-context and role-to-client binding; `IDN-3` (`hide_parameters=True`), `IDN-4` (httpx logger level), `IDN-7`, `IDN-9`, `API-1`.
- `INF-4` diagnostic settings; `IDN-8` per-user limiter on upload and load routes if required.
- `DAT-9` honour `If-Match` on contact/visit when present; `DAT-10` write only changed fields on reload; `DAT-12` lock or conditional update on confirm; `DAT-13` audit the legal-hold block and expiry deletes; `DAT-14` CHECK constraints, FK, `datetime2`.
- `FE-6` CSP `frame-src` and MSAL error mapping (verify against the tenant); `FE-10`, `FE-11`, `FE-13`, `FE-14`, `FE-15`.
- `TST-3`, `TST-4`, `CI-5`, `CI-6`; add `pytest-cov` and a coverage report to CI.

**4. Longer term (architecture):**
- Decide the ownership model: service-level invariant with a database guard, or RLS on child tables through the parent.
- A stated "aggregate version" rule for the site and a lint or test that enforces `_touch` on every mutating path.
- Per-user client store and a documented account-switch protocol for shared devices.
- Job execution model for multiple replicas (claims, leases, idempotent sends).
- Observability beyond the API; alert rules for sync errors, load failures and WAF blocks (TDD §13).
- `entregado` lifecycle (`DAT-15`) and the open TDD pendientes.

Dependencies: 1 before 2 (CI must be green and `alembic check` fixed before the integrity migration in 2); the topology decision in 2 gates every Azure item; the business decisions in `IMPROVEMENT_BACKLOG.md` §6 gate `DAT-5`, `DAT-15` and the retention items.

---

## I. Validation evidence

All commands run on 2026-10-11 (America/Mexico_City) against the local compose stack at commit `69f5b31`. Logs are in the session scratchpad (`audit/*.log`, `audit/mutations.log`, `audit/mutate.sh`, auditor probe scripts).

| Check | Command | Outcome |
|---|---|---|
| Git state | `git status --short`, `git worktree list`, `git rev-list --count main..ux-redesign` | clean; one worktree; 28 ahead of `main`/`origin/main` |
| Concurrent agents | `ls --time-style=full-iso ~/.claude/projects/…/*.jsonl`; `/proc/<pid>/cwd` of every `claude` pid | other transcript last modified 2026-10-10 21:31; only this session's pid in the repo |
| Backend tests | `make test` | 153 passed, exit 0 (14 s) |
| Test counts | `pytest --collect-only -q -m integration` / `-m "not integration"` | 63 / 90 |
| Frontend unit | `pnpm -r --filter '!e2e' test` | 28 passed |
| Playwright | `pnpm exec playwright test` (e2e/) | 18 passed, 27.8 s; `--list`: 18 tests in 9 files |
| Build | `pnpm build` | exit 0, both apps |
| Lint | `make lint` | **exit 2**: ruff E501 `app/modules/archivos/router.py:151` |
| Typecheck | `pnpm -r typecheck` | exit 0 |
| Bicep | `bash infra/bicep/validate.sh` | 13 modules, 3 param files OK, exit 0 |
| Workflows | `actionlint` | no output, exit 0 (shellcheck absent on host) |
| Node deps | `pnpm audit --prod`, `pnpm audit` | no known vulnerabilities |
| Python deps | `uv export --frozen --no-dev` → `uvx pip-audit -r` (286 packages) | no known vulnerabilities |
| Alembic | `alembic heads`/`history`; `alembic check` | single baseline; `check` **FAILED** (remove_column `sitio.rowversion`) |
| OpenAPI | `curl /api/openapi.json` vs `docs/openapi.json` | live has `HEAD /archivos/{id}`; docs stale |
| Secrets | `git grep -inE "password|secret|apikey|api_key|token="`; gitleaks full history (auditor) | dev-only values; gitleaks flags the public Azurite key only |
| Image | `docker run --entrypoint sh … -c 'id; ls /app'` (auditor) | uid 10001; `tests/`, `migrations/`, `samples/` present |
| API probes | see §F and `audit/probes.log` | 422/413/401/403 as expected; one 500 (`API-1`) |
| Concurrency bursts (auditors) | 8–12 threads, same If-Match / same Idempotency-Key | 1 winner, exactly one ledger/audit row |
| RLS probes (auditors) | sqlcmd as `pipeline_app`, pool SPID reuse | 0 rows without context; context cleared on check-in |
| Races (auditor) | barrier scripts `race_docs.py`, `race_ver.py`, `outbox_race.py` | `DAT-2`, `DAT-3`, `DAT-7` reproduced |
| Mutations | `audit/mutate.sh` (10 faults, scratch copy at `/mut`) | 9 caught, 1 survived |
| GitHub | `gh run view` (auditor) | run 38106114922: 6 jobs green incl. Playwright; drift run 38134212283 fails at OIDC login (no Azure) |

**Environmental limitations:** nothing is deployed to Azure, so every `INF-*`/`CI-2..4` item and the OneLake, Defender, Front Door, MSAL and Entra behaviours are static analysis. `pytest-cov` is not installed, so no coverage figure. Azurite has no immutability or legal hold. Read-committed snapshot is off locally and on in Azure SQL (race timing may differ; the rowversion checks do not depend on it). No Intune device. The auditors shared one stack, which caused one contaminated Playwright run (recorded above). `docker compose run -v …:/app` cannot override the compose bind mount; mutations must mount elsewhere.

---

## J. Final assessment

**Quality.** The security core, the concurrency control and the test harness are better than most systems at this age, and the previous audit's "fixed" claims B-01, D-01, A1, A2, A5 and B-05 were independently re-probed and hold; E-1 (offline sync on transient 5xx) is covered only by the engine unit tests, which pass, and was not re-exercised end to end. The defects found are concentrated where two subsystems meet: bulk load and ownership, files and the site version, the client store and identity, and the Azure topology that has only existed on paper.

**Most important unresolved risks:** `DAT-1` (data visibly broken for a reassigned coordinator), `FE-1` (cross-user data and lost captures on a shared or re-logged phone), the three deploy-topology items (`INF-1..3`), the latent `rowversion` drop (`CI-1`), and the unbounded sync stall (`FE-3`).

**Must be fixed before the next release (test environment):** everything in §H.1, the topology decision and its workflow changes (`INF-1..3`, `CI-2..4`), `IDN-2`, the version-check integrity set (`DAT-2`, `DAT-3`, `DAT-11`), `DAT-7`, `FE-2`, `FE-4`, and the regression tests that pin them. Then re-run this audit's evidence table, and the first real `build-deploy` run becomes the next gate.

**Recommended next steps:** (1) green CI and the §H.1 fixes on this branch, (2) one design note deciding the ownership invariant and the aggregate-version rule, (3) the Azure topology decision with TI, (4) the business decisions in `IMPROVEMENT_BACKLOG.md` §6 that gate `DAT-5`, `DAT-15` and retention, (5) a penetration test and a device test once the test environment exists.

---

## K. Finding details for the remaining P1 and P2 items

Section D expands the data and sync defects. This appendix gives the full field set for every other P1 and P2 finding so each can be picked up from this file alone. P3 items keep their one-line fix in §B and §H.

### INF-1 — Admin SPA cannot load behind Front Door `/admin/*` (P1, confirmed by static analysis)
- **Category:** deployment / routing. **Where:** `infra/bicep/modules/frontdoor.bicep:147-151` (routes `/admin`, `/admin/*` → `og-admin`, no `originPath`, no rule set), `apps/web-admin/vite.config.ts:13` (`base = VITE_BASE_PATH ?? "/"`), `.github/workflows/build-deploy.yml:125-131` (build step sets only `VITE_AUTH_MODE`), `packages/auth/src/msal.ts:49-50` (`redirectUri: window.location.origin`).
- **Evidence:** the three files above; `apps/web-admin/public/staticwebapp.config.json` excludes `/assets/*` from the fallback at the SWA root only.
- **Reproduction (once deployed):** open `https://<afd-host>/admin/`; the HTML references `/assets/<hash>.js`, which Front Door routes by `/*` to the PWA SWA, where the hash does not exist and the fallback returns the PWA's `index.html` as a script.
- **Expected vs actual:** the admin UI boots at `/admin/`; instead a blank page with script MIME errors. Even with `base=/admin/`, Front Door forwards `/admin/assets/…` unchanged and the SWA has `assets/…` at its root, and the MSAL redirect lands on `/` (the PWA).
- **Root cause:** path-based routing of two separately built SPAs with no prefix rewrite and no base-aware build or redirect URI.
- **Impact:** admin app unusable in test and prod on first deployment.
- **Fix:** host-based routing (separate Front Door endpoint or custom domain for admin; base stays `/`, one bundle promotes, redirect URI unchanged), as recommended in `IMPROVEMENT_BACKLOG.md` `ADMIN-BASE`.
- **Regression test:** post-deploy smoke step that fetches `/admin/` (or the admin host), parses every `<script src>` and asserts 200 with a JavaScript content type.

### INF-2 — Dev environment cannot work as deployed (P1; SPA path confirmed, SQL path plausible)
- **Category:** infrastructure. **Where:** `infra/bicep/params/dev.bicepparam:8` (`deployFrontDoor=false`), `infra/bicep/modules/staticwebapps.bicep` (no linked backend, no `/api` route), `apps/web-admin/public/staticwebapp.config.json` and the PWA equivalent (404 → `index.html`), `packages/api-client/src/client.ts:46` (`baseUrl = ""`, same-origin calls), `infra/bicep/modules/sql.bicep:39` (`publicNetworkAccess: Enabled`, no firewall or VNet rules anywhere: `grep -rn "firewall|virtualNetworkRule|serviceEndpoints" infra/bicep` is empty), `infra/bicep/modules/network.bicep` (Container Apps subnet NSG `DenyAllOtherOutbound` priority 4000; outbound allowed only 443, 53 and VNet).
- **Evidence:** the greps and file reads above.
- **Reproduction (once deployed):** any push to `main` triggers `deploy-dev`; the migrate job cannot open TCP 1433 to the public SQL endpoint; the SPA on its SWA host calls `/api/v1/me` and receives `index.html` with 200.
- **Expected vs actual:** dev is a working environment with public ingress plus IP restrictions; instead the API never becomes healthy and the SPAs never reach it.
- **Root cause:** dev drops Front Door without replacing the two things it provided (API path routing, and in test/prod a private SQL endpoint).
- **Impact:** every `main` deployment fails; the "deploy to dev on push" promise of ADR-010 is void.
- **Fix:** give dev a SQL private endpoint (or a SQL firewall/VNet rule plus an NSG outbound rule for 1433 and 11000–11999 to the `Sql` service tag) and either a Front Door or an SWA linked backend / `/api` route to the Container App.
- **Regression test:** `deploy-dev` smoke test that calls `/api/v1/me` through the SPA host and expects a 401 Problem Details body.

### INF-3 — Digest verification against a private-endpoint ACR from a hosted runner (P1, plausible)
- **Category:** CI / infrastructure. **Where:** `.github/workflows/deploy-environment.yml:56-63` (`az acr repository show --name … --image pipeline-api@sha256:…`), `infra/bicep/modules/acr.bicep:28`, `test.bicepparam` and `prod.bicepparam` (`acrPrivateEndpoint = true`, `publicNetworkAccess: 'Disabled'`).
- **Evidence:** `az acr repository show` is a registry data-plane call; with public access disabled it is refused from outside the VNet. `az acr import` (the next step) is control-plane and would work.
- **Reproduction:** run `deploy-test` once the registry is private.
- **Expected vs actual:** the digest check passes; instead a network-denied error fails every test and prod deployment at its first step.
- **Root cause:** data-plane verification chosen for a registry that is private by design.
- **Fix:** verify with a control-plane call (`az acr manifest list-metadata` through the resource provider, or trust the `az acr import` result and verify the imported digest), or run the step on a self-hosted runner inside the VNet.
- **Regression test:** a dry run of `deploy-test` against the test environment.

### CI-1 / DAT-8 — `alembic check` fails and autogenerate would drop `sitio.rowversion` (P2, confirmed)
- **Category:** migrations / CI. **Where:** `backend/app/models.py:153-159` (`rowversion` mapped with `system=True`), `backend/migrations/env.py:22-27` (`include_object` does not exclude it).
- **Evidence:** `docker compose exec -T api sh -c 'cd /app && alembic check'` → `FAILED: New upgrade operations detected: [('remove_column', None, 'sitio', Column('rowversion', TIMESTAMP(), nullable=False))]`, exit 255 (re-run by the lead auditor with the same result). `grep -rn "alembic check" .github Makefile` is empty.
- **Reproduction:** the command above; or `alembic revision --autogenerate -m x` and read the generated file.
- **Expected vs actual:** `check` is clean and gates CI; instead it always fails, and the next autogenerated migration contains `op.drop_column('sitio', 'rowversion')`.
- **Root cause:** autogenerate ignores `system=True` columns, so the real column looks removed.
- **Impact:** no drift gate; a routine autogenerate would remove the ETag/If-Match column and the stale-write protection (finding B-01's fix).
- **Fix:** in `include_object`, return `False` for `type_ == "column" and name == "rowversion"`; add `uv run alembic check` to the CI backend job after `alembic upgrade head`.
- **Regression test:** the CI step itself.

### LINT-1 — `make lint` is red at the audited commit (P2, confirmed)
- **Category:** CI. **Where:** `backend/app/modules/archivos/router.py:151` (102 characters), introduced in commit `300198d` by this session.
- **Evidence:** `make lint` → `E501 Line too long (102 > 100)`, `make: *** [Makefile:53: lint] Error 1`, exit 2. `ci.yml:82-88` runs `uv run ruff check .` with the same configuration, so the CI backend job fails before mypy, tests or the e2e job run.
- **Expected vs actual:** green lint; instead the first `ruff check` stops the Make target, and mypy and eslint are never reached locally.
- **Root cause:** the line was not linted before committing (the commit ran typecheck, tests and `pnpm -r lint`, not `make lint`).
- **Impact:** the branch cannot pass CI; any PR from it is blocked.
- **Fix:** wrap the decorator arguments across lines.
- **Regression test:** CI; locally, run `make lint` before every commit (document in `CONVENTIONS.md`).

### CI-2 — Nightly drift check can never pass (P2, confirmed by static analysis)
- **Category:** CI. **Where:** `.github/workflows/drift.yml:45-49` (what-if with no `trafficRevision` and no `DEV_ALLOWED_INGRESS_CIDRS`), versus `deploy-environment.yml:83-87`, `infra/bicep/modules/containerapps.bicep:174-176` (`[{latestRevision:true}]` when the parameter is empty), `dev.bicepparam:12`.
- **Evidence:** after a deploy, live traffic is `revisionName: X, weight 100` (set by `az containerapp ingress traffic set`); the drift template renders `latestRevision: true`, a permanent `Modify`. Dev additionally renders `127.0.0.1/32` instead of the deployed CIDRs. Run 38134212283 currently fails earlier, at the OIDC login, because nothing is deployed.
- **Expected vs actual:** zero changes when nothing drifted; instead a permanent diff on `ca-pipeline-api-*`.
- **Root cause:** the drift job does not reproduce the deploy job's parameter resolution.
- **Impact:** a drift alarm that is always on is ignored.
- **Fix:** resolve the current traffic revision and pass the CIDR variable exactly as the deploy step does.
- **Regression test:** run drift immediately after a deploy and assert zero changes.

### CI-3 — Documented fail-closed dev ingress fallback never happens (P2, confirmed)
- **Category:** infrastructure / CI. **Where:** `.github/workflows/deploy-environment.yml:36` (`DEV_ALLOWED_INGRESS_CIDRS: ${{ vars.DEV_ALLOWED_INGRESS_CIDRS }}`), `infra/bicep/params/dev.bicepparam:12` (`readEnvironmentVariable(..., '127.0.0.1/32')`).
- **Evidence:** `env -u DEV_ALLOWED_INGRESS_CIDRS bicep build-params` → `['127.0.0.1/32']`; `DEV_ALLOWED_INGRESS_CIDRS="" bicep build-params` → `['']`. GitHub always defines the env key, as `""` when the variable is missing.
- **Expected vs actual:** missing variable → ingress restricted to localhost; instead `ipAddressRange: ''`, which ARM most likely rejects (deployment fails) and `validate.sh`'s policy grep cannot catch.
- **Root cause:** the default only applies to an unset variable, never to an empty one.
- **Impact:** a confusing deploy failure, and a documented safety behaviour that does not exist.
- **Fix:** `empty(...)` guard in Bicep, or fail the workflow step when the variable is empty.
- **Regression test:** CI step running `build-params` with the variable empty and asserting no empty CIDR.

### CI-4 — Smoke test and guard accept placeholder identity configuration (P2, confirmed)
- **Category:** CI / configuration. **Where:** `.github/workflows/deploy-environment.yml:185-198` (passes on any 401 with a `type` field), `infra/bicep/params/{dev,test,prod}.bicepparam:10-17` (`authTenantId = '00000000-0000-0000-0000-000000000000'`, `prod.bicepparam:17` `teamsAppId = ''`), `backend/app/core/config.py:97-125` (guard does not check the tenant GUID or `teams_app_id`).
- **Evidence:** the file reads above; a 401 Problem Details body is produced regardless of tenant configuration.
- **Expected vs actual:** a deployment with placeholder ids fails loudly; instead it goes green, nobody can sign in, and with `NOTIFY_MODE=graph` every Teams notification raises on the empty `TEAMS_APP_ID` and ends `fallida` after 8 attempts.
- **Root cause:** the smoke test checks reachability only; the guard checks modes, not values.
- **Fix:** guard rejects the all-zero tenant and an empty `TEAMS_APP_ID` when notifications use Graph; smoke test fetches `https://login.microsoftonline.com/<tenant>/v2.0/.well-known/openid-configuration` for the configured tenant and performs one authenticated call.
- **Regression test:** unit tests that the guard rejects a zero GUID and an empty Teams id with `NOTIFY_MODE=graph`.

### IDN-2 — Deployed dev/test run as `ENVIRONMENT='test'` (P2, confirmed from configuration)
- **Category:** configuration / security. **Where:** `infra/bicep/params/dev.bicepparam:39`, `test.bicepparam:35` (`environmentName = 'test'`), `backend/app/core/config.py:18` (default `local`), `:99-100` (guard returns early unless `production`), `backend/app/core/db.py:31` (`TrustServerCertificate=yes` unless production), `backend/app/main.py:45-47` (docs exposed unless production), `backend/app/cli.py:94` (`e2e-cleanup` refuses only production), `backend/Dockerfile` (no `ENVIRONMENT` set).
- **Evidence:** file reads above; the test param file calls itself "same topology as production … UAT environment".
- **Expected vs actual:** a deployed environment validates the Azure SQL certificate and refuses dev modes; instead UAT and dev trust any server certificate, skip every guard check (scan, notify, directory modes unchecked), expose `/api/docs`, allow the destructive cleanup command, and an image started without `ENVIRONMENT` runs as `local`.
- **Root cause:** one `environment` value conflates local convenience with deployed non-production.
- **Impact:** man-in-the-middle exposure on the UAT database connection (inside a private VNet, so plausible rather than easy); UAT behaviour drifts from production; anyone with `exec` on the test Container App can wipe the e2e id range.
- **Fix:** tie `TrustServerCertificate` to `db_auth == "sql"`; add a `deployed` flag or apply the guard when `db_auth == "entra"`; make `ENVIRONMENT` required (no default); `e2e-cleanup` allows only `local`.
- **Regression test:** `Settings(environment="test", db_auth="entra")` → ODBC URL contains `TrustServerCertificate=no`; `Settings()` without `ENVIRONMENT` raises.

### INF-4 — Only SQL sends diagnostic logs (P2, confirmed by static analysis)
- **Category:** observability. **Where:** `grep -rn diagnosticSettings infra/bicep` → `sql.bicep:121,133` only; `monitoring.bicep` leaves public ingestion/query on and `disableLocalAuth: false` even for the private prod profile; `frontdoor.bicep:19` WAF `Prevention`.
- **Expected vs actual:** Front Door access and WAF logs, Key Vault `AuditEvent`, storage `StorageDelete`/`StorageWrite` (including the immutable documents account) and Container Apps job events flow to the workspace; instead none do.
- **Impact:** WAF false positives on 4 MB binary upload parts are silent; blob deletes, legal-hold changes and Key Vault access are invisible; the alerts TDD §13 asks for cannot be built.
- **Fix:** diagnostic settings on Front Door (`FrontDoorAccessLog`, `FrontDoorWebApplicationFirewallLog`), Key Vault, both storage accounts and the Container Apps environment; consider `disableLocalAuth: true` on the workspace in prod.
- **Regression test:** a Bicep lint/policy step asserting each resource module declares a `diagnosticSettings` resource.

### TST-1 — e2e download assertion passes when no download happens (P2, confirmed)
- **Category:** test quality. **Where:** `e2e/tests/pwa.flow.spec.ts` (PDF test, last lines): `const dl = page.waitForEvent("download", { timeout: 15_000 }).catch(() => null); … expect(ev === null || (await ev.suggestedFilename()).endsWith(".pdf")).toBe(true);`
- **Expected vs actual:** the in-app download (HU-11) is verified; instead a timeout becomes `null`, which satisfies the assertion.
- **Root cause:** defensive `.catch` plus a disjunction that accepts the failure branch.
- **Impact:** the only real check of the download is the API-level fetch earlier in the test; a broken button goes unnoticed.
- **Fix:** remove `.catch(() => null)`; assert `suggestedFilename()` ends with `.pdf` and the first bytes of `ev.path()` are `%PDF`.
- **Regression test:** the corrected assertion.

### TST-2 — Production-guard tests cannot localise a removed check (P2, confirmed)
- **Category:** test quality. **Where:** `backend/tests/unit/test_security.py:116-127` and `:202-220`.
- **Evidence:** `test_production_guard_refuses_dev_modes` sets eight invalid values at once and asserts only that the message starts with "Refusing to start in production"; deleting any single check (`SCAN_MODE`, `DB_AUTH`, `STORAGE_MODE`, `NOTIFY_MODE`, `DIRECTORY_MODE`, `allowed_azp`, JWKS, issuer) keeps the test green. There is no test that a fully valid production configuration is accepted.
- **Impact:** the guard is the last line against deploying with dev identity or storage modes; it can regress silently.
- **Fix:** parametrise one case per rule starting from a valid base and breaking one field, plus one acceptance case.
- **Regression test:** the parametrised suite.

### TST-5 — Phone requirement for Dueño Localizado is unpinned (P2, confirmed by mutation)
- **Category:** test coverage. **Where:** `backend/app/modules/transiciones/rules.py:76-77`; tests `backend/tests/unit/test_rules.py`, `backend/tests/integration/test_transiciones.py`.
- **Evidence:** mutation M10 (replace the phone check with `pass`) → `19 passed`; the same tests catch the removal of the whole contact precondition (M3) and the name check is exercised indirectly.
- **Expected vs actual:** TDD §7.1 proposes name and phone as the minimum (pendiente 5); the code enforces both, the tests enforce only "contact exists" and "name present".
- **Impact:** a regression that lets sites advance without a phone number would ship unnoticed.
- **Fix:** unit test with a contact whose `telefono` is empty or whitespace → `["Falta el teléfono del dueño"]`; integration test `PUT /contacto` with blank phone is rejected by the schema and, if ever accepted, `POST /transiciones` → 422.
- **Regression test:** as above.

### FE-6 — MSAL error mapping and CSP `frame-src` (P2, plausible)
- **Category:** auth. **Where:** `packages/auth/src/msal.ts:242-246` (`throw e` for anything but `InteractionRequiredAuthError`), `apps/pwa-coordinador/src/sync/engine.ts:260` (non-`ApiError` → terminal `error`), `apps/pwa-coordinador/public/staticwebapp.config.json:14` (CSP has no `frame-src`).
- **Evidence:** msal-browser 4.30.0 `StandardController` falls back to `acquireTokenBySilentIframe` when the refresh token is gone; that iframe loads `login.microsoftonline.com`, which `default-src 'self'` blocks; the resulting `BrowserAuthError` (and `no_network_connectivity`) is not interaction-required.
- **Expected vs actual:** these errors mean "sign in again" or "offline"; instead the op is marked `error`, the site's chain halts, and during `pullDelta` a raw `lastError` banner appears.
- **Fix:** add `frame-src https://login.microsoftonline.com`; in `getToken`, map other `AuthError`s to `InteractionRequired`, and network-type codes to `OfflineError`.
- **Regression test:** unit test with a mocked PCA throwing `BrowserAuthError`; `syncAll` reports `needsLogin` or `offline`, never `error`. Verify the iframe path against the real tenant.

### FE-7 — Admin 412 dialog loops on the same stale ETag (P2, confirmed by code)
- **Category:** admin concurrency UX. **Where:** `apps/web-admin/src/pages/SitioDetail.tsx:352-366` (`useAdminAction` captures `sitio.etag`), `:368-376` (alert text "Cierra el diálogo para recargar el sitio"), `:251, 264, 276` (`onClose={() => setDialog(null)}` with no invalidate); `main.tsx:13` (`staleTime: 30_000`).
- **Reproduction:** open Devolver; change the site through the API; submit → 412; close; reopen; submit → 412 again until a focus refetch or reload.
- **Expected vs actual:** closing reloads the site; instead nothing is refetched and the 412 body's `current` is ignored.
- **Fix:** on `isPreconditionFailed`, `qc.setQueryData(["sitio", id], e.current)` or invalidate; add a "Recargar" action to the alert.
- **Regression test:** admin e2e: devolver → API change → submit (412) → close → reopen → submit → success.

### FE-8 — Load review truncates at 500 rows (P2, confirmed by code)
- **Category:** admin correctness at scale. **Where:** `apps/web-admin/src/pages/CargaDetail.tsx:27` (`?limit=500`, `next_cursor` never read), `:50` (`localPending` counts loaded warnings only), `:67` (`setAll` covers loaded rows), `:94` (Confirmar enabled when `localPending === 0`); backend `cargas/service.py:283-288` (422 "Hay filas con advertencia sin decisión"); `core/config.py:70` (`load_max_rows = 5000`).
- **Reproduction:** load a file with more than 500 rows where a warning sits past row 500; the review shows "0 pendientes", Confirmar is enabled, the server answers 422.
- **Expected vs actual:** every warning decidable and the gate based on the server's count; instead invisible warnings and a confusing 422.
- **Fix:** paginate with `filas.next_cursor` (or load all pages), base the gate on `lote.pendientes_decision`, and add a bulk "approve all warnings" endpoint.
- **Regression test:** a 600-row load with warnings beyond row 500 can be decided and confirmed.

### FE-9 — Landing-page queues computed from the first 200 sites by id (P2, confirmed by code)
- **Category:** admin correctness at scale. **Where:** `apps/web-admin/src/pages/Resumen.tsx:20-30` (`/api/v1/sitios?limit=200`, then client-side filter), backend `sitios/service.py:103` (`order_by(Sitio.id)`).
- **Reproduction:** seed more than 200 sites and set `en_revision_admin` on a high id; the queue omits it while showing an authoritative count.
- **Expected vs actual:** queues list every site needing a decision; instead the newest sites (exactly those a load sends to review) are the ones dropped. Already noted as "attention queues cap" in `UX_VALIDATION.md` §4 at S3; the audit rates it P2 because the count is presented as authoritative.
- **Fix:** server-side filters `en_revision_admin=true` / `devuelto=true` with counts, or a dedicated queue endpoint.
- **Regression test:** 250 seeded sites with the flag on id 240; the queue shows it.


---

## L. Remediation status (same day, commits `2444a68` … `caa1612` on `ux-redesign`)

Everything rated P1 and P2 that does not need Azure access was fixed with regression tests in six
commits; gates on the last one: `make lint` clean, backend 183 passed, frontend unit 40, Playwright
18, Bicep and actionlint clean, image builds with pinned digests. Azure-dependent items are
implemented statically and will be verified by the first real `build-deploy` run (backlog
`DEPLOY-RUN`).

| Finding | Status | Where |
|---|---|---|
| DAT-1, DAT-4, DAT-5, DAT-6 | fixed (`sitios.cambiar_propietario`, 422s; pending notices follow the site and sent ones leave the previous coordinator's feed) | `2444a68`, feed filter in the final commit |
| FE-1, FE-3, CI-1/DAT-8, LINT-1, DOC-1 | fixed | `2444a68` |
| IDN-2, CI-4 (guard side) | fixed (`deployed` semantics, image default) | `1f47e7d` |
| DAT-2, DAT-3, DAT-11/FE-5 | fixed (site lock and touch, filtered unique index, migration `b7c2e4a1d9f0`) | `1f47e7d`, hints corrected in `a2d8cc8` |
| DAT-7 | fixed (row claims, per-row commit) | `1f47e7d`, hints in `a2d8cc8` |
| FE-2, FE-4, API-1, TST-1, TST-2, TST-5 | fixed | `1f47e7d` |
| IDN-1, IDN-3, IDN-4, IDN-5, IDN-7, IDN-9 | fixed | `a2d8cc8` |
| DAT-9, DAT-10, DAT-12, DAT-14 (checks, FK), DAT-13 (expiry, legal-hold block) | fixed (migration `c9d1e2f3a4b5`) | `a2d8cc8` |
| FE-6, FE-7, FE-8, FE-9, FE-11, FE-12, FE-13, FE-14, FE-15 | fixed | `47681d9` |
| INF-1, INF-2, INF-3, INF-4, INF-5, CI-2, CI-3, CI-4 (smoke test), CI-5, CI-6, TST-3, TST-4 | implemented statically / fixed | `caa1612` |
| Found during remediation: the new `avanzar` lock ran after the If-Match check, so a waiting request passed with the new version | fixed, caught by the TST-4 burst test | `caa1612` |
| Found in review: the deployment guard required `TEAMS_APP_ID` while Bicep hardcoded `NOTIFY_MODE=graph`, so dev would have refused to start | fixed: `notifyMode` parameter, `log` in dev and test until the Teams app exists | final commit |
| FE-10 | open by decision (captures stay unconditional unless the client sends If-Match) | backlog `FE-10` |
| DAT-16, IDN-8, TST-4 (SPID), DAT-13 (send outcomes), coverage gate, CI image pins, plus backlog A3 (Front Door id), HEALTH-DEPS, LOG-FIELDS, PURGE-ERR, OBS alerts | fixed in the hardening round (commit after `b170511`) | see CHANGELOG |
| DAT-13 (mark-read, `escaneando`), DAT-14 (`datetime2`), DAT-15, DAT-17, IDN-6 (lint rule: ruff S608 already enabled; kept as a note) | open, P3 | backlog §3 |
| Azure verification of INF-1..4, CI-2..4; MSAL against a tenant; pen test; device test; screen-reader pass | needs the test environment | backlog §1–§2 |
