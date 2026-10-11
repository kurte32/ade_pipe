# Production readiness plan

Date: 2026-10-10. Starting point: the post-audit state on branch `implementation` (PR #1). The
Critical and High defects are fixed and verified locally; what remains is (a) the open audit findings,
(b) a deploy pipeline that has only been corrected on paper, (c) zero validation in Azure, and (d)
business decisions the TDD left pending. This plan orders that work so each phase gates the next, and
maps every item to the acceptance criteria in `architecture/PRODUCTION_READINESS.md` §8.

Effort is in person-days for the named role and is an estimate for planning, not a commitment.
Verification vocabulary follows the repo convention: *implemented and locally verified* ·
*statically validated* · *validated in test Azure* · *deployed and verified*.

## Progress (2026-10-11, branch `prod-readiness`)

| Phase | Status |
|---|---|
| 0 Decisions and access | **Not started — needs people.** Business, Legal and Security decisions; subscription, Entra registrations and Teams approval requests. |
| 1 Open code findings | **Done, verified locally.** B-02, B-04, B-05, B-06, B-08, A5/D-12, A4/A6, C4, C5, C7, C8, C9, E-2…E-4 fixed with regression tests; E-5 closed as not reproducible; new finding A7 found and fixed. |
| 2 Deploy pipeline | **Done, statically validated.** D-03, D-04, D-06, D-07, D-09 fixed; new findings D-13 and D-14 found and fixed; actionlint and the Playwright suite added to CI. Nothing has run on GitHub or in Azure. |
| 3 Azure `test` | **Blocked** on a subscription, Entra registrations and explicit authorization to create Azure resources. |
| 4 Hardening and acceptance | Not started (depends on Phase 3; pen test should be booked now). |
| 5 Production and pilot | Not started. |

Gates after Phase 1–2, from a clean `make reset`: backend 153 passed (random order), frontend unit
26 passed, Playwright 14 passed twice with a stable database, ruff/mypy/eslint/tsc clean, Bicep 13
modules + 3 params with the open-ingress policy, actionlint clean, pnpm audit and pip-audit clean.
Two plan targets were not fully met: B-04 rejects a 100k-row XLSX in 4.8 s (target 2 s; the rest is
openpyxl loading shared strings, bounded by the 10 MB cap), and the `/readyz` schema check was
dropped because the app role is deliberately denied access to `alembic_version`.

## Critical path

Three external dependencies have lead times longer than any coding task and must start on day one:

1. **Azure test subscription** with permission to create the resource group, private networking,
   and Front Door Premium (TI). Blocks Phase 3 entirely.
2. **Entra app registrations** for `pipeline-api`, `pipeline-pwa`, `pipeline-web-admin` with app
   roles, Assignment Required, and the two Conditional Access policies (identity team). Blocks
   Phase 3 sign-in validation.
3. **Teams app publication approval** and Graph permission consent (TI, Seguridad; TO_BE open
   question 4). Blocks return notifications in Phase 3.

Everything in Phases 1 and 2 can proceed in parallel with these.

## Phase 0 — Decisions and access (week 1, in parallel with Phase 1)

| Item | Owner | Acceptance |
|---|---|---|
| Resolve TDD pendientes that are configuration today: required document catalog, minimum fields per status, return-reason catalog, terminal statuses (TO_BE Q5) | Negocio | Catalog rows and `requisito_transicion` confirmed in writing; seed updated |
| Retention start event, legal hold, discarded-site treatment (TO_BE Q1, pendiente 7); privacy notice text (pendiente 13) | Legal | Decision recorded in ADR-003 addendum; `purga_utc` rule and immutability period set |
| Shared phones policy (TO_BE Q6); PDFs captured without signal (Q2) | Negocio | Sign-out/cache policy decided; Assumption 2 confirmed or the upload queue extended |
| Private networking mandate vs service firewall (ADR-008) | Seguridad | One sentence decision; `privateNetworking` param fixed per environment |
| Request the three critical-path items above | TI, identity, Seguridad | Tickets opened with target dates |

## Phase 1 — Close the open code findings (weeks 1–2, local, no Azure)

All verifiable on the local stack; each lands as its own commit with a regression test shown failing
first, then `make test && make e2e` green.

| ID | Work | Role | Days | Acceptance |
|---|---|---|---|---|
| B-02 | Insert the idempotency row (key as PK) before the business write; on unique violation re-read and return the stored response, or 409 while in flight | backend | 1.5 | Concurrent same-key burst: all 2xx, identical body; no 500 |
| B-05 | Reject oversized `Content-Length` before reading; stream upload parts with a running counter; global max-body limit | backend | 1.5 | 12 MB body for a 4 MB part is aborted before full buffering; memory flat |
| B-04 | Bound the bulk-load row iterator at `load_max_rows + 1` for xlsx/xls/csv; parse in a threadpool | backend | 1 | 100k-row file rejected after ~5001 rows in under 2 s |
| B-06 | Per-row try/except and commit in `promote` and `purge`; DB state change before the destructive blob delete; fake-scanner harness | backend | 2 | Batch where row 2 raises: row 1 stays promoted, its blob survives; rerun is idempotent |
| A5 + D-12 | Server-generated correlation id (client value logged under a separate key); trust `X-Forwarded-For` only from configured proxy CIDRs; restrict `--forwarded-allow-ips` | backend | 1 | Forged headers no longer reach the audit ledger; test asserts |
| B-08 | Replace the `assert` in `confirm()`; handle `prev is None` for update/revision rows | backend | 0.5 | Deleted-between-preview-and-confirm case returns 422, not 500 |
| C4, C5 | Make `test_reload` self-provisioning; add `pytest-randomly` to dev deps and CI | backend | 1 | Suite passes in random order and each test in isolation |
| C7 | E2E provisioning/teardown per spec (or reseed step); assert stable row count across two runs | frontend | 1 | Two consecutive `make e2e` runs leave the row count unchanged |
| C8, C9 | Unit tests for `DefenderScanner.result` (4 tag states), `promote.run` with a fake scanner, `directory.resolve`, Graph notifier; outbox non-leak assertion | backend | 2 | Coverage of `jobs/promote.py` and `archivos/scan.py` above 90% |
| E-2…E-5 | Plain-language sync messages; a distinct "reintentando" state instead of "sin conexión" on 5xx; Devolver tooltip; filter-row layout; dropdown count off-by-one | frontend | 1.5 | Visual check in Chrome; vitest for the state label |
| A3/A4/A6 | Bind dev-idp to `127.0.0.1`; stop echoing exception class names from `/readyz` | backend | 0.5 | Compose and readiness test updated |

Phase 1 exit: `TECHNICAL_FINDINGS.md` has no open Medium; backend coverage ≥ 90% on the jobs and
scan modules; suite order-independent.

## Phase 2 — Make the deploy pipeline correct (weeks 2–3, static until Phase 3)

| ID | Work | Role | Days | Acceptance |
|---|---|---|---|---|
| D-03 | Deploy the new revision at weight 0 (`latestRevision: false`), run the migration job, then shift traffic; `/readyz` additionally checks `alembic_version == head` | infra + backend | 2 | Workflow order asserted by a pipeline test; readiness fails on an un-migrated schema |
| D-04 | Single promotion path: `az acr import` of the same digest into test/prod registries (or one shared registry with per-env AcrPull); build the SPA per environment, or move `VITE_*` to a runtime `config.json` served by SWA | infra + frontend | 3 | Test/prod pull the exact dev digest; SPA bundle embeds the target tenant and client ids |
| D-06 | Gate `build-deploy` on `ci` success via `workflow_run`; branch protection on `main` requiring CI | infra | 0.5 | Red CI blocks `deploy-dev` |
| D-07 | Fail-closed CIDR placeholder in `dev.bicepparam`; require Front Door in dev or document the exception | infra | 0.5 | Param lint rejects `0.0.0.0/0` |
| D-09 | Pin all third-party actions to commit SHAs; checksum the Bicep CLI download | infra | 0.5 | No floating tags in `.github/workflows` |
| — | `actionlint` and a what-if dry-run step in CI (no deploy) | infra | 0.5 | CI runs both on every PR |

Phase 2 exit: `bash infra/bicep/validate.sh` and `actionlint` clean; ADR-010 updated to match the
implemented order; everything still *statically validated only*.

## Phase 3 — Stand up `test` in Azure and validate what has never run (weeks 3–6)

Gated by the three critical-path items. This is where every "written, not verified" claim becomes
*validated in test Azure* or a defect.

| Step | Work | Role | Days | Evidence to attach |
|---|---|---|---|---|
| 3.1 | First deployment via `deploy-environment` with OIDC federation; migration job runs before traffic | infra | 2 | Deployment log; `what-if` clean afterwards |
| 3.2 | Entra sign-in on both SPAs with MSAL; Assignment Required; a coordinator cannot enter the admin web; Conditional Access A and B on a managed device | identity + frontend | 2 | Screenshots and token claims; PRODUCTION_READINESS §8 Security rows 4–5 |
| 3.3 | Managed-identity SQL auth; Key Vault references resolve for API **and** migrate job (D-02 in practice) | infra | 1 | API `/readyz` green; migrate job log |
| 3.4 | Defender for Storage: EICAR file tagged Malicious and never promoted; clean file promoted within `SCAN_WAIT_SECONDS` | backend | 1 | Audit rows; blob tags |
| 3.5 | Immutability and legal hold on `st-doc`: deletion of a promoted blob blocked; purge job logs the skip | infra | 1 | Job log; storage error |
| 3.6 | Graph/Teams: a return produces a Teams notification with no owner contact data; outbox backoff on forced failure | backend | 1 | Teams message; outbox rows |
| 3.7 | Front Door + WAF + Private Link origin approval; health probe green; rate-limit rule fires under a burst | infra | 2 | Front Door diagnostics |
| 3.8 | Fabric: Mirroring excludes the four sensitive tables; OneLake shortcut reads `st-doc` | backend + Fabric admin | 1 | Fabric workspace screenshots |
| 3.9 | Nightly `drift` workflow against `test` | infra | 0.5 | One clean nightly run |

Phase 3 exit: `IMPLEMENTATION_STATUS.md` rows move from *statically validated* to *validated in test
Azure*; any item that fails becomes a new finding and returns to Phase 1 or 2.

## Phase 4 — Hardening and acceptance on `test` (weeks 6–9; pen test lead time dominates)

| Gate (PRODUCTION_READINESS §8) | Work | Role | Days |
|---|---|---|---|
| Penetration test | Book early (lead time 2–4 weeks); scope = `test` with production topology; retest | Seguridad | external |
| Restore drill | Point-in-time restore to a new DB, repoint, verify ledger digest; measure against RTO | infra | 1 |
| SQL failover + Graph outage simulations | API recovers unattended; offline queue replays; breaker opens/closes | backend | 1.5 |
| Offline chain on a real device | Three sites, full chain in low signal on an Intune-managed Android device; zero duplicates, conflict surfaced on admin return | frontend | 2 |
| 150 MB resumable upload with forced disconnect; 150 MB download via Front Door on 4G | Verify ingress timeouts and `Range` | frontend + backend | 1 |
| Performance (RNF-08) | `GET /sitios` p95 < 3 s on 4G with the full dataset; bulk-load preview < 30 s | frontend + backend | 1.5 |
| Alerts and dashboards | Deploy §2.4–2.5; force each alert condition once | infra | 2 |
| Runbooks RB-01…RB-15 | Write the missing ones; walk through with L2 | architect | 2 |
| Dependency and image scans; Defender for Cloud review | Close or accept with a dated exception | backend + infra | 1 |

Phase 4 exit: every §8 checkbox has evidence attached; no Critical/High pen-test finding open.

## Phase 5 — Production and pilot (weeks 9–10)

| Step | Acceptance |
|---|---|
| Deploy production from the same image digest and SPA bundles as `test` (D-04 proven) | Digest match recorded in the deployment log |
| Rollback rehearsal in `test` immediately before: traffic shift to the previous revision in minutes with the migration confirmed backward compatible | Timed evidence |
| Resource-group deletion locks; break-glass documented | Lock present; procedure audited |
| Go-live checklist signed by the architect, operations owner, and Seguridad | Signed checklist |
| Pilot: one region's coordinators for two weeks with the on-call rota active; exit on zero lost captures and zero unresolved conflicts | Pilot report |

## Summary timeline and effort

| Phase | Calendar | Effort (person-days) | Gate |
|---|---|---|---|
| 0 Decisions and access | week 1 | 2 (coordination) | Tickets open, decisions recorded |
| 1 Open code findings | weeks 1–2 | ~14 (backend 11, frontend 3) | No open Medium; coverage ≥ 90% on jobs/scan |
| 2 Deploy pipeline | weeks 2–3 | ~7 (infra 5, backend/frontend 2) | Static validation clean; ADR-010 matches |
| 3 `test` in Azure | weeks 3–6 | ~12 + tenant approvals | Every claim *validated in test Azure* |
| 4 Hardening and acceptance | weeks 6–9 | ~12 + pen test | §8 checklist complete |
| 5 Production and pilot | weeks 9–10 (+2 pilot) | ~4 | Go-live signed; pilot clean |

About ten weeks with a backend engineer, a frontend engineer, and an infrastructure engineer at
roughly half time each, plus identity, Seguridad, Legal, and Negocio for their decisions. The
schedule is driven by the external lead times (subscription, Entra, Teams approval, pen test), not by
coding; starting those in week 1 is what makes ten weeks possible.

## What this plan does not change

The architecture stays as approved. No new components, no re-platforming. The plan converts the
remaining *statically validated* and *not verified* rows into evidence, and closes the audit's open
findings in severity order.
