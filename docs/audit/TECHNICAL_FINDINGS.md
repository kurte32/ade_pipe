# Technical findings — independent audit

Date: 2026-10-10. Method: adversarial, read-only first; every CONFIRMED finding reproduced against the
running local stack (SQL Server 2022, Azurite, local OIDC issuer) or in a real Chrome browser.
Azure-runtime items are marked SUSPECTED because no Azure subscription exists.

Severity by actual risk: **Critical** = data loss / privilege escalation reachable now · **High** =
security-control bypass or broken core promise in a realistic scenario · **Medium** = correctness or
reliability defect with user impact · **Low** = minor · **Info** = hygiene.

Status: **CONFIRMED** (reproduced, command + output recorded) · **SUSPECTED** (inspection only) ·
**RECOMMENDATION**.

Finding IDs keep their audit-stream prefix: A = identity/authz/RLS, B = business logic/data integrity,
C = test quality, D = infra/CI-CD/docs, E = browser UX/offline reliability.

> **Remediation:** see also the 2026-10-11 section at the end and `PRODUCTION_READINESS_PLAN.md`. **First pass (same session as the audit):** B-01, D-01, E-1, A1, A2, B-03, C6, C10, C11, D-02, D-05, D-08 and
> the doc corrections (D-10, D-11, B-07) are fixed and verified — see the status table and verification
> protocol in `REMEDIATION_PLAN.md`. The rest are left as planned actions there.

## Summary by severity

| Sev | IDs |
|---|---|
| Critical | B-01 |
| High | D-01, E-1 |
| Medium | A1, B-02, B-03, B-04, B-05, B-06, C4, C6, D-02, D-03, D-04, D-05, D-06, D-07 |
| Low | A2, A5, B-07, C5, C7, C8, C9, D-08, D-09, D-10, D-11, D-12, E-2, E-3, E-4 |
| Info | A3/A4/A6, B-08, C10, C11, E-5, E-6 |

---

## CRITICAL

### B-01 Optimistic concurrency is checked in Python, not in the UPDATE — silent lost update
- Status: CONFIRMED (reproduced twice, independently) · Area: correctness / concurrency-control bypass
- Location: `backend/app/modules/transiciones/service.py:60-69` (`_require_if_match`, a Python compare) and `:98-101` (the ORM then emits `UPDATE … WHERE sitio.id = ?` with no rowversion predicate); `backend/app/models.py:153-159` (rowversion column has no mapper `version_id_col`). Routes: `POST /api/v1/sitios/{id}/transiciones`, `POST /api/v1/admin/sitios/{id}/{devolver,descartar,reasignar}`.
- Evidence: 10 concurrent `POST /transiciones` on one site with the **same** If-Match ETag → `{201: 10}` (expected exactly one 201 and nine 412). Reproduced by the module auditor on sites 29/59/64/65 and independently by the integrator on site 2. The same-ETag burst wrote 10–12 rows into the append-only `dbo.auditoria` ledger — non-removable duplicates. `grep -rn "version_id_col\|StaleDataError" backend/app` returns nothing.
- Impact: TO_BE §5 (rowversion exposed as ETag) and §6.2 (If-Match → 412 when the site changed) are not met for concurrent writers. The Python check catches only staleness already committed before the read; two requests that read the same rowversion both pass and both UPDATE. Reachable today with no special access: two devices, a retried offline operation, or admin `descartar` racing admin `devolver` silently overwrite each other and leave duplicate rows in the immutable audit and status-history ledgers. This is data loss reachable now — the production-readiness blocker.
- Remediation: add `__mapper_args__ = {"version_id_col": Sitio.rowversion, "version_id_generator": False}` so every UPDATE carries `AND rowversion = ?` and a zero-row update raises `StaleDataError`, mapped to the existing 412; keep the Python `_require_if_match` for the friendly Problem Details body. Verify on SQL Server that the post-update rowversion is re-read within a multi-statement transaction (`devolver` does update + history insert + outbox); if not, fall back to an explicit Core `UPDATE … WHERE id=? AND rowversion=?` with a rowcount check. Regression: a deterministic two-session test (A commits, B must raise → 412) plus the threaded API burst asserting `{201:1, 412:N-1}`.

---

## HIGH

### D-01 `.env.example` is git-ignored and untracked — a clean clone cannot run the documented setup
- Status: CONFIRMED · Area: infra / docs
- Location: `.gitignore:5` (`.env.*`), `Makefile` `.env:` target, `README.md:7-9`, `docs/LOCAL_DEVELOPMENT.md:20-21`, `.github/workflows/ci.yml:30`.
- Evidence: `git ls-files --error-unmatch .env.example` → “did not match any file”; `git check-ignore -v .env.example` → `.gitignore:5:.env.*`. The file exists only in the working tree; the `!apps/*/.env.development` exception does not cover the repo-root file.
- Impact: a fresh `git clone` has no `.env.example`, so `make up` (which runs `cp .env.example .env`), both quick-starts, and `ci.yml:30` (`grep … .env.example >> $GITHUB_ENV`) all fail. The “verified from a clean clone” claim is false: the clean-volume runs used a working tree that already contained the untracked file. Masked so far only because CI has never run on GitHub.
- Remediation: add `!.env.example` to `.gitignore`, `git add -f .env.example`, commit. Guard: a CI step `git ls-files --error-unmatch .env.example`, or a temp-clone `make up` smoke test.

### E-1 A transient 5xx permanently halts a coordinator's offline sync chain; no automatic retry
- Status: CONFIRMED (reproduced live in Chrome) · Area: reliability
- Location: `apps/pwa-coordinador/src/sync/engine.ts` — `classifyFailure` (terminal `error` for any `ApiError` whose status is not in {401,412,422,404,409,428,410}) and `syncAll` (`pending` = only `pendiente`/`enviando`; any site with a `bloqueada`/`error` op is added to `blockedSites` and skipped). List badge: `apps/pwa-coordinador/src/pages/MisSitios.tsx:15-23` counts only `bloqueada`, lumping `error` into the ordinary “pending” branch.
- Evidence: on site detail, stopped the API (`docker compose stop api`), saved a contact. IndexedDB `operaciones` held one op `estado="error"`, `error="HTTP 500 (500)"` (the Vite proxy returns 500 on upstream connection-refused). Restarted the API (healthy) and clicked “Sincronizar ahora”: only `GET …/delta` fired, no PUT for the op; the op stayed `error`. Only the per-site “Reintentar con el estado actual” button drained it.
- Impact: RNF-02 says no capture is lost for lack of signal. No data is lost (it persists in IndexedDB), but the production topology is Front Door → Container Apps, where a backend outage, rolling deploy, scale event, or brief SQL failover surfaces as an HTTP 5xx, not a `NetworkError`. The engine docstring claims “network failures keep operations pendiente”, but a 5xx is classified terminal, halting that site's whole chain until the coordinator manually opens the site and taps Reintentar. The list view shows it as a normal “pendiente de sincronizar”, giving no needs-attention signal. No test covers the 5xx case.
- Remediation: in `classifyFailure` treat 429 and 5xx (and timeouts) as transient — keep `pendiente` with an attempt/backoff counter — and reserve terminal `error` for non-retryable 4xx; fix the `MisSitios` badge to surface `error` as needs-attention; correct the docstring. Regression (vitest): a 503 keeps the op retryable and the next sync drains it once the server recovers.

---

## MEDIUM

### A1 Production guard validates the issuer but not the JWKS URL
- Status: CONFIRMED · Area: security · Location: `backend/app/core/config.py:91-114` (`_production_guard`).
- Evidence: the guard requires `auth_issuer` to start with `https://login.microsoftonline.com/` but never checks `auth_jwks_url`; a production config with the correct issuer string and a dev or attacker JWKS endpoint is accepted. No `https://` floor on the JWKS URL either.
- Impact: tokens are verified with keys fetched from the JWKS host, so the issuer check gives false assurance about the trust root. Medium, not High: a wrong JWKS fails closed (every real token 401s and is noticed at once) and the attack additionally needs an attacker-reachable JWKS host.
- Remediation: in the guard, require `auth_jwks_url` to be `https://` and to match the Entra keys host; unit-test a rejected config.

### B-02 Idempotency-Key does not deduplicate concurrent submissions; losers get 500
- Status: CONFIRMED · Area: reliability · Location: `backend/app/core/idempotency.py:25-66`, `transiciones/router.py:41-57`, `archivos/router.py:54-63`.
- Evidence: `lookup` (SELECT) and `store` (INSERT) share the request transaction; under READ COMMITTED two concurrent requests both see no row and both run the write. 6 concurrent `PUT /sitios/552/contacto` with the same key+body → `{200:1, 500:5}`; the five failures were a primary-key violation on `sitio_contacto` surfaced as an unhandled `pyodbc.IntegrityError` → generic 500. Exactly one applied; no double-apply. Sequential replay with a different body is correctly 422.
- Impact: TO_BE §6.2 says a replayed key returns the stored response. Under concurrency (offline retry while the original is in flight, or two tabs) the duplicate gets an opaque 500 though the write succeeded.
- Remediation: insert the idempotency row (key as PK) before the business work, or `INSERT … WHERE NOT EXISTS`/`MERGE`; on unique-violation re-read and return the stored response (or 409 while in flight). Regression: the concurrent same-key burst asserting all responses are 2xx with identical body.

### B-03 `delta?conocidos=` exceeds SQL Server's 2100-parameter limit → 500
- Status: CONFIRMED · Area: reliability · Location: `backend/app/modules/sitios/service.py:156-162` (`Sitio.id.in_(known_ids)`).
- Evidence: `GET /api/v1/sitios/delta?conocidos=<1..2500>` → HTTP 500; `conocidos=1,2,3` → 200. The known-id list is splatted into one `IN (?, …)`; SQL Server rejects more than 2100 parameters.
- Impact: `removed_ids` (how a device learns to drop sites hidden by RLS after reassignment) is computed from the client's full known-id list. A coordinator whose offline cache exceeds ~2100 sites gets a 500 on every delta sync and can never reconcile removals — a realistic steady state for a national pipeline.
- Remediation: chunk `known_ids` into <2000 batches and union, or pass as a table-valued parameter / `OPENJSON`. Regression: a delta call with 2500 known ids asserting 200 and correct `removed_ids`.

### B-04 Bulk-load parser materialises the whole sheet before the row-count limit is checked
- Status: CONFIRMED · Area: reliability · Location: `backend/app/modules/cargas/parser.py:80-89` and `:157-158` (limit checked after the full parse).
- Evidence: a 2.92 MB xlsx (under the 10 MB byte cap) with 100,000 rows was rejected only after 43.79 s with peak heap 72.9 MB. The byte cap does not bound work. Not a whole-API stall (openpyxl/zlib release the GIL; `/healthz` stayed ~1 ms), only per-request CPU/memory.
- Impact: “validation happens before loading into memory” is not met for row count; an admin can drive hundreds of MB and minutes of CPU per request.
- Remediation: bound the row iterator at `load_max_rows + 1` during read and raise early (CSV/XLS too); consider a threadpool. Regression: a 10k-row xlsx asserting 422 after reading at most ~5001 rows.

### B-05 Upload part body is fully buffered before the size check; no request-body limit
- Status: CONFIRMED · Area: reliability / security · Location: `backend/app/modules/archivos/router.py:81-97` (`data = await request.body()`), size validated later.
- Evidence: a part declared at 4 MB sent with 12 MB → 422, but curl reports `size_upload = 12582912` — the whole body was received before rejection. No body-size middleware or proxy limit anywhere.
- Impact: an authenticated coordinator can POST arbitrarily large part bodies, each read fully into memory before rejection — a memory-exhaustion vector.
- Remediation: reject on oversized `Content-Length` before reading, then stream with a running counter that aborts past expected+1; add a global max-body limit. Regression: the 12 MB PUT asserting the body is aborted before full buffering.

### B-06 Background jobs mutate blob storage before the DB commit and lack per-row isolation
- Status: SUSPECTED (code-evidenced; needs defender scan mode or an injected mid-batch failure to reproduce) · Area: reliability / data integrity · Location: `backend/app/jobs/promote.py:33-37`, `backend/app/modules/archivos/service.py:309,348`, `backend/app/jobs/purge.py:37-67`.
- Evidence: `promote.run` processes all `escaneando` sessions in one `system_session` with a single commit and no per-row try/except (contrast `outbox.py:38-56`, which isolates each row). It copies the blob to documents and deletes the staging blob, then flushes.
- Impact: a later failure in the batch rolls back already-promoted `sitio_archivo` rows whose staging blob is already deleted → unrecoverable upload; or an orphan blob with no metadata row. `purge.run` has the same shape.
- Remediation: wrap each row in its own try/except and commit per row; order the DB state change before the destructive blob delete. Regression: a batch where row 2 raises, asserting row 1 stayed promoted and its blob survives.

### C4 Intra-module test ordering coupling in `test_cargas.py`
- Status: CONFIRMED · Area: testing · Location: `backend/tests/integration/test_cargas.py:240-289` depends on `:157-237`.
- Evidence: run in isolation, `test_reload_updates_without_touching_progress` fails with `IndexError: list index out of range` at `:251` because it reads sites that an earlier test in the same module inserted. Green only because pytest runs in definition order.
- Impact: not order-independent; fails under sharding, `-k`/`--last-failed`, or any randomiser. The “125 pass” guarantee is coupled to execution order.
- Remediation: make the test self-provisioning (upload+confirm its own lot in a fixture); run CI with `pytest -p randomly`.

### C6 `?limit=200` single-page assertions are coupled to the DB row count
- Status: CONFIRMED (mechanism) · Area: testing · Location: `test_identity_and_rls.py:63-78`, `test_cargas.py:219-251`, contract in `app/modules/sitios/service.py:89,100-101`.
- Evidence: the list is ordered ascending by id, capped at 200. Freshly-inserted fixtures get the highest ids and land on the last page. Several assertions fetch a single `?limit=200` page and expect the newest sites present. Passes today only because the table is small (99 rows, confirmed; was 91 at the start of the audit).
- Impact: `test_reload` breaks first once the baseline exceeds ~114 rows (200 − 86 cargas rows); the table grows ~4 rows per e2e run (C7), so this is a few CI runs away. `test_list_only_mine`'s admin assertion breaks later (~198).
- Remediation: iterate the cursor until the fixture id is found, or filter server-side by the unique fixture name/region. Regression: seed >200 sites for one coordinator and still find the newest.

### D-02 Migration job cannot resolve its Key Vault secret (identity never granted access)
- Status: SUSPECTED (template inspection) · Area: infra · Location: `infra/bicep/modules/keyvault.bicep:47-55`, `containerapps.bicep:224-231,256-262`.
- Evidence: Key Vault Secrets User is granted to `apiIdentityPrincipalId` only; there is no assignment for `migrationIdentityPrincipalId`. Yet every job, including `migrate`, gets the App Insights KV secret ref bound to its own identity.
- Impact: the migrate job declares a secret resolved with an identity that has no vault access → it cannot start; `deploy-environment.yml:65-78` hard-gates the deployment on that job, so every environment's deploy fails at the migration step.
- Remediation: grant `migrationIdentityPrincipalId` Key Vault Secrets User, or drop the App Insights secret from the migrate job. Guard: a Bicep assertion that every job's `secrets[*].identity` has a matching KV role.

### D-03 Deployment shifts 100% traffic to the new revision before migrations run
- Status: CONFIRMED (ordering violation by inspection) · Area: reliability / architecture · Location: `.github/workflows/deploy-environment.yml:55-78`, `infra/bicep/modules/containerapps.bicep:157,162-164`, vs `architecture/ADR/ADR-010-iac-cicd.md:69,82`.
- Evidence: Bicep pins all traffic to the latest revision; the workflow deploys that Bicep (new revision takes 100%) in the “Deploy infrastructure and API revision” step and only afterwards starts and polls the migration job. ADR-010 requires migration to succeed before the traffic shift.
- Impact: the new image serves traffic against the un-migrated schema for the whole migration window; `/readyz` only checks `SELECT 1`, so readiness stays green through the gap. A failed migration leaves the new code live at 100%.
- Remediation: deploy the new revision at weight 0 (`latestRevision:false`), migrate, then shift traffic. Guard: a pipeline test asserting migrate precedes the traffic-carrying revision.

### D-04 "Build once, promote" is not wired for per-environment registries; dev-compiled SPA promoted
- Status: SUSPECTED (template + workflow inspection) · Area: infra / architecture · Location: `.github/workflows/build-deploy.yml`, `deploy-environment.yml:30,80-84`, `infra/bicep/modules/acr.bicep:14`, vs `ADR-010:16,67`.
- Evidence: ADR-010 requires the same image digest promoted unchanged, but each environment has its own registry and there is no `az acr import`; `deploy-environment.yml` builds the image ref from the target env's `ACR_NAME`, so test/prod reference a digest absent from their registry. Separately, the SPA bundles are built once with dev's compile-time `VITE_*` and reused for every environment.
- Impact: test/prod API deploys pull a nonexistent image; even if fixed, test/prod serve a PWA/admin bundle bound to the dev Entra tenant and client ids.
- Remediation: add `az acr import` or a shared promotion registry; build the SPA per environment or move `VITE_*` to runtime config.

### D-05 Promotion chain is skipped on release tags / dispatch — test and prod deploy nothing
- Status: SUSPECTED (Actions skip semantics) · Area: infra · Location: `.github/workflows/build-deploy.yml:130-158`.
- Evidence: `deploy-test` has `needs: [build, deploy-dev]` and no `always()`/`!cancelled()`; on a `release-*` tag `deploy-dev`'s `if` is false and is skipped, so a needed-job-skipped cascade skips `deploy-test` and `deploy-prod`. The only functional path is a push to `main` (dev).
- Remediation: guard test/prod with `if: ${{ !cancelled() && needs.build.result == 'success' }}` and depend only on `build`.

### D-06 Deployment is not gated on CI (lint/tests)
- Status: CONFIRMED · Area: infra · Location: `.github/workflows/ci.yml`, `build-deploy.yml:13-45`, vs `ADR-010:81`.
- Evidence: the two workflows are independent — `build-deploy` has no `workflow_run`/`needs` on `ci`; `build` runs a Trivy image scan but no lint/unit/integration tests. A push to `main` with failing or cancelled CI still triggers `deploy-dev`.
- Remediation: gate deploy on CI success (`workflow_run`) or fold the test jobs into `build`; enforce the ADR-010 merge gate with branch protection.

### D-07 `dev.bicepparam` ships a public ingress open to the whole internet with DEBUG logging
- Status: SUSPECTED (applies on a real dev deploy) · Area: infra / security · Location: `infra/bicep/params/dev.bicepparam:7-10,35-36`.
- Evidence: `privateNetworking=false`, `deployFrontDoor=false`, `allowedIngressCidrs=['0.0.0.0/0']`, `logLevel='DEBUG'`. With private networking off, `containerapps.bicep:167` applies the CIDR list, exposing the dev API to the whole internet with no WAF and DEBUG verbosity. Token auth is still enforced, bounding the blast radius.
- Remediation: ship a fail-closed placeholder CIDR so a real value must be supplied; consider requiring Front Door even in dev.

---

## LOW

### A2 `primary_role` returns an unknown role string that flows into the DB session context
- Status: CONFIRMED (mechanism) · Area: security · Location: `backend/app/core/security.py` (`Claims.primary_role`), `validate_token` does not require a role.
- Evidence: `validate_token` relies entirely on per-route `require_role` (all 33 routes are gated today). `primary_role` returns `roles[0]` for any role outside `KNOWN_ROLES`, and that string is set as `SESSION_CONTEXT('rol')`, which RLS honours for `Admin`/`Sistema`. One ungated route plus a forged `roles:["Sistema"]` token would bypass RLS. Low only because `Sistema` is a server-side DB session role, not an Entra appRole, so no real token carries it.
- Remediation: `primary_role` → `"Ninguno"` for unknown roles; optionally reject tokens with no known role at validation. Unit-test both.

### A5 Client-controlled `X-Forwarded-For` and `X-Correlation-Id` are written into the append-only audit ledger
- Status: CONFIRMED · Area: security · Location: `backend/app/deps.py` (`client_ip` takes `xff.split(",")[0]`), `backend/app/core/logging.py` (echoes inbound `X-Correlation-Id`).
- Evidence: a coordinator PUT with `X-Forwarded-For: 203.0.113.9` and `X-Correlation-Id: forged-by-client-12345` wrote exactly those values into the immutable `dbo.auditoria` row.
- Impact: poisons the forensics SECURITY.md relies on. No identity impact (oid comes from the token). Related to D-12.
- Remediation: generate the correlation id server-side (log any client value under a separate key); trust `X-Forwarded-For` only from configured proxy ranges.

### B-07 TO_BE §5 claims a trigger enforces `coordinador_oid` on child tables; no trigger exists
- Status: SUSPECTED · Area: architecture · Location: `architecture/TO_BE.md` §5 vs `backend/migrations/versions/1130828e690d_baseline.py`.
- Evidence: `grep -niE trigger` on the baseline matches only the comment; the denormalised `coordinador_oid` is maintained only in code.
- Remediation: add the trigger the design calls for, or amend TO_BE. Do not leave the claim unresolved.

### C5 No test randomiser installed (hides C4)
- Status: CONFIRMED · Area: testing. `pytest-randomly`/`pytest-xdist` absent, so every run uses the same deterministic order. Add `pytest-randomly` to dev deps and run it in CI.

### C7 Playwright specs have no teardown — every e2e run permanently grows the dev DB
- Status: CONFIRMED · Area: testing/reliability. `admin.cargas` inserts 4 coordinator sites per run via the real bulk load and never deletes them; 12 orphan e2e sites measured (origen_id 800000–899999); total grew 91→99. Feeds C6. Provision+teardown per spec, or reseed before e2e.

### C8 Coverage holes in production-only paths
- Status: CONFIRMED · Area: testing. `pytest --cov` = 86% (3018 stmts, 409 miss). Zero coverage: `cli.py`, `jobs/promote.py` (malware-scan promote/reject), `jobs/scheduler.py`, `jobs/idempotency_cleanup.py`, `jobs/run.py`. Low: `notificaciones/graph.py` 58%, `archivos/scan.py` 61% (`DefenderScanner.result`), `equivalencias/directory.py` 71%, `storage.py` 74%. Unit-test these with fakes; none need Azure.

### C9 `test_outbox_retries_with_backoff` under-asserts
- Status: CONFIRMED · Area: testing. Asserts only `ultimo_error.startswith("RuntimeError")`; the full injected message (including a “secret” token) is persisted. Mitigated: `ultimo_error` is DB-only, not in any response schema. Assert `"secret" not in ultimo_error` or rename.

### D-08 `SCAN_MODE` hardcoded to `defender` regardless of `enableDefenderScanning`
- Status: SUSPECTED · Area: infra. `containerapps.bicep:77` always sets `SCAN_MODE=defender`; the Defender resource is created by an independent param. If ever false, uploads stall in `escaneando`. Derive `SCAN_MODE` from the toggle.

### D-09 Third-party GitHub Actions pinned to floating tags, not SHAs
- Status: CONFIRMED · Area: infra/security. gitleaks@v2, setup-uv@v3, azure/login@v2, docker/build-push@v6, static-web-apps-deploy@v1, plus a `curl` of the Bicep “latest” release. Already listed as remaining work. Pin to commit SHAs + checksum.

### D-10 OPERATIONS.md asserts storage controls the templates do not implement
- Status: CONFIRMED · Area: docs. `OPERATIONS.md:92` lists document “versioning”; `storage.bicep:139-146` never sets `isVersioningEnabled` (off on the HNS account — the documented reason for container immutability). RB-08 also references a DB connection “secret/KV reference” that is a plain env var, and recommends `sp_verify_database_ledger` while the same file says digest storage is not configured. Correct the wording.

### D-11 Documentation inaccuracies (consolidated)
- Status: CONFIRMED · Area: docs. `DELIVERY_REPORT.md:74` says `pnpm audit --audit-level moderate` but `ci.yml:130` enforces `high` (weaker). `ENVIRONMENTS.md:57-58` says dev uses `.env.local`; the tracked files are `apps/*/.env.development`. `IMPLEMENTATION_STATUS.md` infra rows use neither verification vocabulary; the “actionlint clean” claim is not reproducible here. README says “10 dev coordinators” vs LOCAL_DEVELOPMENT “10 equivalences”.

### D-12 `--forwarded-allow-ips "*"` trusts proxy headers from any source
- Status: SUSPECTED · Area: infra/security · Location: `backend/Dockerfile:30`. Bounded behind Front Door + internal ingress, but with D-07's public dev ingress any reachable party can spoof `X-Forwarded-For`/`-Proto`. Restrict to the known proxy ranges. Fix together with A5.

### E-2 Raw "HTTP 500 (500)" shown to field coordinators
- Status: CONFIRMED · Area: ux · Location: `engine.ts` `classifyFailure`, rendered verbatim by `ConflictPanel`. Map transient server errors to a plain-language retry message.

### E-3 Admin "Devolver" disabled with no explanation
- Status: CONFIRMED · Area: ux · Location: `apps/web-admin/src/pages/SitioDetail.tsx:67`. Correctly disabled when the site is at the first status (no prior status to return to), but nothing explains why it is greyed. Add a tooltip.

### E-4 Sitios filter header: "Incluir no vigentes" checkbox label overlaps the Filtrar button
- Status: CONFIRMED · Area: ux. Cosmetic layout collision at desktop width in the admin Sitios filter row.

---

## INFO

### A3 / A4 / A6 Security hygiene (Info)
- No Front-Door-id header check at the API (SECURITY.md labels origin restriction a network-only recommendation). The dev IdP compose port lacks a `127.0.0.1:` bind, so `/token` is LAN-reachable locally. `/readyz` echoes exception class names unauthenticated. The dev IdP is proven non-deployable by the production guard (the one residual config path is A1).

### B-08 `confirm()` uses `assert` for a state invariant
- Status: CONFIRMED (static) · `backend/app/modules/cargas/service.py:373`. Stripped under `python -O`; a revision/update row whose site was deleted between preview and confirm reaches `_apply_update(prev=None)` → 500. Replace the assert with explicit handling.

### C10 No JWT algorithm-confusion negative test
- Status: SUSPECTED (control exists) · `security.py` pins `algorithms=["RS256"]`, but there is no `alg:none` or HS256-with-RSA-public-key test. Add both (both must 401).

### C11 Playwright `flows` project matches zero files
- Status: CONFIRMED · `e2e/playwright.config.ts:32-36` `testMatch: /flow\..*\.spec\.ts/` matches nothing; the flow spec runs under `pwa-mobile`, and the desktop `flows` project runs nothing. Fix the regex to `/\.flow\.spec\.ts/`.

### E-5 Local site count mismatch (list header "Todos (14)" vs 13 cached / 13 in DB)
- Status: SUSPECTED · The PWA estatus dropdown showed 14 while the Dexie cache and the DB both hold 13 sites for coordinator ard. Minor off-by-one in the dropdown count.

### E-6 Shared mutable dev DB accumulates e2e test rows
- Status: CONFIRMED (observed) · Sites named “prueba”, “Equivocado borrar”, “Sitio E2E-*” persist from prior runs. Not a product defect; see C7.

---

## Found during remediation (2026-10-11)

### A7 Crafted equivalence emails escaped the Graph `/users/` path (Medium) — fixed
- `GraphDirectory.resolve` built the URL through httpx path normalisation and the email pattern
  accepted `/`, `%`, `?`, `#`: `a/../../me@x.com` became `/v1.0/me@x.com`, steering the API's managed
  identity to another Graph path; a non-user object's id could be stored as a coordinator identity.
  Admin-only input. Fixed by percent-encoding the segment and tightening the pattern; unit tests.

### D-13 Production SPAs could never start (High, latent) — fixed
- CI set `VITE_SPA_CLIENT_ID_PWA/_ADMIN` but the code reads `VITE_SPA_CLIENT_ID`; auth config is
  evaluated in the browser, so the build passed and every deployed SPA would fail on load. Fixed by
  the runtime `config.json` (D-04); verified with a production build in Chrome.

### D-14 The image scan action could not be resolved (Medium, latent) — fixed
- `aquasecurity/trivy-action@0.28.0` does not exist (tags are `v`-prefixed), so the build job would
  have failed before scanning. Pinned to `v0.36.0` by SHA.

### R24 False 412 when advancing while the previous save is in flight (High) — fixed
- Found by the first CI e2e run. Tapping "Avanzar" before the contact PUT returned queued the
  transition with the pre-contact ETag; sent in the next sync pass, it got a spurious 412 and the
  coordinator saw a conflict nobody caused. The engine now follows the chain of this device's own
  successful writes when resolving an op's base ETag; other actors' changes still produce 412.
  Reproduced deterministically in vitest and in Playwright (delayed PUT), both fixed.

### CI setup defects on first GitHub run — fixed
- pnpm 12 ignored the build-script approval in package.json; the runner's existing Microsoft keyring
  broke the ODBC step; shellcheck flagged unused loop variables. All fixed; CI green.

## Corrections to the original findings
- **B-08:** the "`prev is None` → 500" part does not reproduce; rows without an existing site already
  take the insert path. Only the `assert` was a defect (fixed).
- **E-5:** closed as not reproducible; the list and its count read the same local store.
- **E-1 follow-up:** the "Sin conexión" banner follows `navigator.onLine` and never showed falsely;
  a distinct "retrying" banner was added for server errors while online.
