# Release readiness statement · Pipeline de Posibles Tiendas

Date: 11 October 2026 · Branch `ux-redesign` (release candidate for `main`) · **Audience:** release manager, TI, Seguridad, business owner · **When to read:** before scheduling the first test deployment and the go-live · **Source of truth:** this file for the evidence summary; `docs/audit/ENGINEERING_AUDIT_2026-10-11.md` for the findings; `docs/IMPROVEMENT_BACKLOG.md` for what stays open.

## 1. Statement

The software is release-ready: every defect the engineering audit rated P1 or P2 is fixed with a regression test, the hardening the audit asked for is in place, and every gate that can run without an Azure subscription is green on the production artefacts themselves (the container image without development dependencies, and the built PWA under the Static Web App's security policy).

What remains is **execution in Azure**, which this environment cannot reach: the prerequisites in §4 and the first real deployment in §5. None of it is engineering work left undone; it is the verification that only a deployed environment can give. Two business decisions (§6) are open and do not block the test deployment.

## 2. Evidence (all at commit `92d613e` or later on `ux-redesign`)

| Gate | Command | Result |
|---|---|---|
| Backend unit and integration | `make test` | 188 passed; coverage 89 % (CI floor 80 %) |
| Frontend unit | `pnpm -r --filter '!e2e' test` | 42 passed |
| Playwright, dev servers | `make e2e` | 18 passed |
| Playwright, **built PWA** with service worker under the SWA Content-Security-Policy | `make e2e-preview` | 9 passed (caught the WebAssembly policy gap before Azure would have) |
| Playwright, **production image** (no dev dependencies, non-root, pinned base digests) serving the whole suite | `make e2e-image` | 18 passed, 270 requests served |
| Accessibility | axe WCAG 2 A/AA inside the a11y specs | 0 serious or critical violations on every page |
| Static analysis | `make lint` (ruff, mypy strict, eslint, tsc) | clean |
| Infrastructure | `bash infra/bicep/validate.sh`, `actionlint` | 14 modules and 3 parameter files OK; workflows clean |
| Schema | `alembic upgrade head`, `alembic downgrade`, `alembic check` | cycle clean, no drift (also a CI step) |
| Secrets and dependencies | gitleaks (full history), `pip-audit`, `pnpm audit` | no leaks, no known vulnerabilities |
| Mutation probes (audit) | 10 injected faults | 10 of 10 caught after the test added for the survivor |
| Image vulnerability scan | `trivy image --severity HIGH,CRITICAL --ignore-unfixed pipeline-api:rc` (same scanner and severity as `build-deploy`) | 0 high, 0 critical (Debian 12.15 base, 123 packages, Python packages) |
| Dynamic security scan | OWASP ZAP baseline against the built PWA with the SWA headers and against the API | 0 failures on both; warnings reviewed: `style-src 'unsafe-inline'` is needed for inline style attributes, browsing-context isolation headers added, COEP left out on purpose (MSAL iframe), cacheability informational |
| Restore drill (RB-08, backlog RESTORE) | `BACKUP DATABASE … COPY_ONLY`, `RESTORE … WITH MOVE` to `pipeline_drill`, `sp_generate_database_ledger_digest` + `sp_verify_database_ledger`, RLS probe as `pipeline_app` | restore 2018 pages; ledger verification OK on the live database and on the restored copy; the restored copy returns 0 rows without session context and the coordinator's 8 with it; the app login cannot update the ledger there either. Azure point-in-time restore itself still needs Azure |
| Database outage simulation (RB-11, backlog SIM) | `docker compose stop sqlserver`, probe, `start` | `/readyz` 503 during the outage; API calls answer 503 `service-unavailable` with `Retry-After` (was 500, fixed); `/readyz` 200 about 6 s after the database returns, with no API restart |
| Latency sanity (RNF-08 server side) | 200 × `GET /api/v1/sitios?limit=200`, 10 concurrent, dev container | p50 132 ms, p95 200 ms, max 217 ms for the 200-item page; the 4G device measurement still needs a phone |

## 3. What changed since the audit (one line each; details in `CHANGELOG.md`)

- Ownership follows every reassignment path; reassignment to unknown oids and discard proposals on terminal sites are refused.
- Files lock and bump the site; one current copy per document type; lots are locked on confirm; the outbox claims rows; every lock is a real `UPDLOCK` hint.
- The RLS context uses the route's role; Admin is bound to the admin SPA client; the deployment guard applies to every deployed environment; the image fails closed.
- The PWA store belongs to one account; requests time out; orphaned changes are dropped and announced; photo replays read the live session; transient failures back off; tabs are serialised; MSAL errors map to offline or sign-in.
- Admin queues are server-side, the load review reads every page, a 412 reloads the site.
- Front Door origin validation, per-user rate limits, dependency health, log fields, alert rules, diagnostics, pinned images, coverage gate, runbooks RB-10 to RB-16, streaming SHA-256, re-download action, axe scans, production-artefact test runs.

## 4. Prerequisites that need Azure, TI, Identidad or Seguridad (backlog §1)

| Id | Owner | Blocks |
|---|---|---|
| SUB | TI | everything below |
| ENTRA (three registrations, roles, groups, Conditional Access) + PARAMS (real GUIDs in `infra/bicep/params/*.bicepparam`, including `authAdminAzp`) | Identidad, then engineering | API start-up (the guard refuses placeholders on purpose) |
| OIDC (federation, role assignments, environment secrets and variables, required reviewers) + BRANCH | TI, repo admin | `build-deploy` |
| SQL-ADM, MI-KV | TI, engineering | migrate job |
| GRAPH, TEAMS (`notifyMode = 'graph'`, `teamsAppId`) | Identidad, TI | Teams notifications (the in-app feed works without them) |
| DEFENDER, IMMUT | Seguridad, TI, Legal | malware scanning in test/prod; retention lock |
| Pend 4/5/8, 7, 13 | Negocio, Legal | catalogue values, retention event, privacy notice text |

## 5. First deployment: what it verifies, in order

Run `build-deploy` on `main` (dev) and then on a `release-x.y.z` tag (test). Each step below is a check the pipeline performs or a check to perform by hand; each was validated statically only.

1. Image promotion by digest into the environment registry (control-plane `az acr import`).
2. Bicep deployment: Front Door profile with two endpoints, routes, WAF, diagnostics; Container App with `FRONT_DOOR_ID`, `AUTH_ADMIN_AZP`, `CORS_ALLOWED_ORIGINS` (dev only), `NOTIFY_MODE`; SQL firewall and NSG rules (dev); alert rules when `alertEmails` is set.
3. Migrate job: baseline plus `b7c2e4a1d9f0` and `c9d1e2f3a4b5`.
4. Traffic shift and smoke test: real tenant OIDC metadata, 401 Problem Details from `/api/v1/me`, admin page and every script on the admin host.
5. By hand (RB-10, RB-11): `GET /readyz`; with an administrator token `GET /healthz/deps`; sign in on both SPAs (redirect URIs per `AZURE_DEPLOYMENT.md` §7); capture, upload a PDF, return a site, see the notice.
6. Nightly `drift.yml` reports zero changes the next morning (RB-14).
7. Force each alert once (OBS), confirm `TRUSTED_PROXY_HOPS` against the ledger IP (AZ-4), restrict the direct SWA hostnames (AZ-6).
8. Penetration test and Intune device test on the test environment (PEN, DEVICE), then go-live from the same digest and bundles (GO-LIVE).

## 6. Decisions still open (do not block the test deployment)

- `entregado`: add the admin action or remove the status (backlog ENTREGADO, TDD pendiente 5).
- Offline captures without `If-Match`: keep unconditional (current) or carry the base ETag (backlog FE-10).
- Marking a notification read is not audited (backlog DAT-13b), by choice.

## 7. Local environment notes

The compose stack is pinned to the same images CI uses (SQL Server 2022 CU27, Azurite 3.35.0). `make reset && make up && make db-seed` restores a clean database; `.env` needs `AUTH_ADMIN_AZP` (see `.env.example`).
