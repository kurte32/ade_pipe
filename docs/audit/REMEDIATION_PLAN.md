# Remediation plan

Ordered corrective actions with dependencies, acceptance criteria, and verification. Each fix lands in
its own commit with the regression test that would have caught it, shown failing before and passing
after, followed by a full-suite rerun. Bicep and workflow changes are statically validated only
(no Azure subscription).

**Status legend:** [ ] not started · [~] in progress · [x] done and verified this audit · [plan] left
as a planned action (design change or needs Azure). The "Remediation status after this audit" section
at the end records what was actually applied.

## Tier 1 — do now (P0/P1, safe and in scope)

1. **B-01 (Critical) — enforce optimistic concurrency at the database.**
   - Action: add `__mapper_args__ = {"version_id_col": Sitio.rowversion, "version_id_generator": False}`
     to the `Sitio` mapper so every UPDATE carries `AND rowversion = ?`; map `StaleDataError` to the
     existing 412 Problem Details with freshly fetched `current`; keep `_require_if_match` for the
     friendly body. Verify on SQL Server that the post-update rowversion is re-read inside a
     multi-statement transaction (`devolver`); if not, use an explicit Core `UPDATE … WHERE id=? AND
     rowversion=?` with a rowcount check.
   - Acceptance: a deterministic two-session test (A commits, B must raise → 412) fails on current
     code and passes after; the threaded burst returns `{201:1, 412:N-1}`; `devolver` still writes
     exactly one history + one audit row; full suite green.
   - Dependencies: none. Gates the production-readiness verdict.

2. **D-01 (High) — track `.env.example`.**
   - Action: add `!.env.example` to `.gitignore`; `git add -f .env.example`.
   - Acceptance: `git ls-files --error-unmatch .env.example` succeeds; a real `git clone` into a scratch
     dir contains the file and `cp .env.example .env` works. Add a CI guard step.

3. **E-1 (High) — treat transient 5xx as retryable in the offline engine.**
   - Action: in `classifyFailure`, classify 429 and 5xx (and timeouts) as transient — keep `pendiente`
     with an attempt/backoff counter — reserving terminal `error` for non-retryable 4xx; fix the
     `MisSitios` badge to count `error` as needs-attention; correct the engine docstring; map the
     user-facing message off the raw status (also addresses E-2).
   - Acceptance: a vitest case where a 503 keeps the op retryable and the next sync drains it once the
     server recovers; and a browser re-run of the exact scenario (stop API, save, start API, Sincronizar
     ahora → queue drains without the per-site button).

4. **B-03 (Medium) — chunk `known_ids` in the delta query.** Acceptance: a delta call with 2500 known
   ids returns 200 with correct `removed_ids`.

5. **A1 (Medium) — validate the JWKS URL in the production guard** (require https and the Entra keys
   host). Acceptance: a unit test rejecting a config with a correct issuer but a foreign JWKS URL.

6. **A2 (Low) — `primary_role` returns `"Ninguno"` for unknown roles.** Acceptance: a unit test that an
   unknown role does not reach `SESSION_CONTEXT('rol')`.

7. **C10 / C11 (Info) — add the JWT alg-confusion tests (`alg:none`, HS256-with-RSA-public-key, both
   401); fix the Playwright `flows` regex to `/\.flow\.spec\.ts/`.**

8. **C4 / C6 (Medium) — make `test_reload` self-provisioning and iterate the cursor (or filter by the
   unique fixture name) instead of scanning a single `?limit=200` page.** Acceptance: both pass in
   isolation and with >200 rows for one coordinator.

9. **Hygiene:** add `backend/.coverage` (and `.coverage*`) to `.gitignore`.

10. **D-02 / D-05 / D-08 (Medium/Low, static) —** grant the migration identity Key Vault Secrets User;
    guard test/prod jobs with `if: ${{ !cancelled() && needs.build.result == 'success' }}` and depend
    only on `build`; derive `SCAN_MODE` from `enableDefenderScanning`. Acceptance: `validate.sh` passes;
    changes reviewed against ADR-010. Statically validated only.

11. **Docs (D-10, D-11, B-07) —** see `DOCUMENTATION_CORRECTIONS.md`; amend or implement the
    `coordinador_oid` trigger claim rather than leaving it.

## Tier 2 — do if it stays small (P1/P2)

- **B-02 —** catch the `IntegrityError` on the idempotency insert, re-read and return the stored
  response (or 409 while in flight), rather than restructuring the store.
- **B-05 —** reject on oversized `Content-Length` before reading, then stream with a counter; add a
  global max-body limit.
- **B-04 —** bound the row iterator at `load_max_rows + 1` during read.
- **A5 + D-12 —** generate the correlation id server-side (log the client value separately); trust XFF
  only from configured proxy ranges; restrict `--forwarded-allow-ips`.
- **D-06 —** gate `build-deploy` on CI via `workflow_run`.
- **D-07 —** ship a fail-closed CIDR placeholder in `dev.bicepparam`.
- **B-08 —** replace the `assert` with explicit handling of unknown actions and `prev is None`.
- **C8 —** unit-test `DefenderScanner.result` (four tag states), `promote.run` with a fake scanner,
  `directory.resolve`, and the Graph notifier; `C9` assert non-leakage; add `pytest-randomly` (C5).

## Tier 3 — remediation plan only (P1/P2, design change or needs Azure)

- **D-03 / D-04 —** redesign the deploy pipeline: deploy the new revision at weight 0, run migration,
  then shift traffic; add `az acr import` (or a shared promotion registry) and build the SPA per
  environment (or move `VITE_*` to runtime config). Verify in a real test subscription.
- **B-06 —** per-row commit in `promote`/`purge` with the DB state change ordered before the
  destructive blob delete; needs a fake-scanner harness to reproduce and regression-test.
- **C7 —** add e2e provisioning/teardown or reseed before the suite; assert a stable row count across
  two runs.

## Final verification protocol

After the Tier-1 fixes, verify from a clean state (not the polluted dev DB):
`make reset && make up && make db-seed && make test && make e2e`, then the clean-clone check for
D-01 and the browser re-run for E-1. Record results in the "Remediation status" section and update the
fixed/verified status in `TECHNICAL_FINDINGS.md` and `RISK_REGISTER.md`.

## Remediation status after this audit

Findings were committed first; each fix is a separate commit with its regression test. All fixes were
verified from a clean state: `make reset && make up` (51 s, migrations applied) `&& make db-seed`
(10 equivalences + 87 sites) `&& make test` (131 passed) `&& make e2e` (14 passed); `pnpm -r test`
(21 passed); ruff / mypy / eslint / tsc clean; `bash infra/bicep/validate.sh` (13 modules + 3 params).

**Fixed and verified this session**

| Finding | Sev | Fix | Verification |
|---|---|---|---|
| B-01 | Critical | `version_id_col` on the Sitio mapper; StaleDataError → 412 | New deterministic ORM test (red→green); API burst now `{201:1, 412:9}`; e2e stale-ETag test passes |
| D-01 | High | `!.env.example` in .gitignore, file force-added | `git ls-tree` shows it in the committed tree |
| E-1 | High | 429/5xx treated as transient with a retry cap; list badge; message | New vitest test (503 stays retryable, next sync drains); re-verified live in Chrome |
| A1 | Medium | Production guard validates AUTH_JWKS_URL | Unit test: foreign JWKS URL refused |
| A2 | Medium | validate_token filters token roles to known app roles | Unit test: "Sistema" from a token dropped |
| B-03 | Medium | Chunk `known_ids` under the 2100-parameter cap | Integration test: 2500 known ids → 200 |
| C10 | Info | alg:none and HS256-with-RSA-public-key negative tests | Both return 401 |
| C11 | Info | Removed the dead Playwright `flows` project | 14 e2e still pass |
| C6 | Medium | List assertions page through the cursor | Pass on the current (99-row) DB and by construction beyond 200 |
| D-02 | Medium | Grant the migration identity Key Vault Secrets User | Bicep builds; statically validated |
| D-05 | Medium | Deploy jobs depend only on build with a `!cancelled()` guard | Workflow YAML parses; statically validated |
| D-08 | Low | SCAN_MODE derived from `enableDefenderScanning` | Bicep builds; statically validated |
| D-10, D-11, B-07 | Low | Documentation corrected; TO_BE trigger claim amended | — |

**Follow-up from the E-1 fix:** a transient 5xx now returns `kind: "offline"`, so the sync status can
briefly read "sin conexión" while the device is actually online. Correct for retry, slightly
misleading label. A distinct transient state (e.g. "reintentando") is a small follow-up, not a defect.

**Left as planned actions** (design change, larger scope, or needs Azure): B-02, B-04, B-05, B-06,
A5 + D-12, D-06, D-07, D-03, D-04, C4 (self-provisioning rewrite), C5/C7/C8/C9 test hardening, and the
remaining E-/Info UX items. These stay in the tiers above with acceptance criteria.

**Production-readiness after remediation:** the Critical (B-01) and both High findings (D-01, E-1) are
fixed and verified locally. The verdict remains **not production-ready** because the deploy path is
still only statically corrected (D-02/D-05/D-08 fixed on inspection; D-03/D-04/D-06 still open) and
nothing has been exercised in a real Azure environment. The system is a credible candidate for a
staged rollout once the remaining deploy-path items are done and validated in a test subscription.

## Second pass (2026-10-11, branch `prod-readiness`)

| Finding | Fix | Verification |
|---|---|---|
| B-02 | Idempotency key claimed before the write; concurrent replays get the stored response | 6 concurrent same-key PUTs → all 200, one body; stable over 10 runs |
| B-05 | 12 MiB global body limit (ASGI); part route rejects by Content-Length, then streams with a counter | Live: oversized bodies rejected with 0 bytes uploaded (was 12,582,912) |
| B-04 | Parser stops at max_rows + 1 for XLSX/CSV/XLS; parse in threadpool | 100k-row XLSX: 4.8 s, 11 MB (was 43.8 s, 73 MB); target 2 s not met |
| B-06 | Per-upload transactions; deterministic archivo id; lost-commit rerun completes | Real DefenderScanner on Azurite tags: isolation, malicious, pending, rerun |
| B-08 | Explicit planned-action check | Corrupted row → 422, lot unchanged |
| A5 / D-12 | Server-side correlation id; XFF only for TRUSTED_PROXY_HOPS; uvicorn --no-proxy-headers | Live: forged headers not stored |
| A4 / A6 | Loopback-only compose ports; no exception names from /readyz | Stack recreated and healthy |
| A7 (new) | Graph path segment encoded; stricter email pattern | Unit tests |
| C4 / C5 | Self-provisioned test_reload; pytest-randomly | Alone, reversed, three seeds |
| C7 | Per-run e2e pool; cleanup in Playwright setup/teardown | Two runs, database unchanged |
| C8 / C9 | Graph adapter tests (incl. no contact data in Teams payload); outbox stores no raw error text | promote 0→95 %, scan 61→89 % |
| E-2…E-4 | Retrying banner, needs-attention counts, Devolver tooltip, filter layout | Chrome |
| D-03 | 0% revision, migrate, health, shift, automatic rollback | Static only |
| D-04 / D-13 (new) | Digest import; environment-neutral SPA with runtime config.json | Production build checked in Chrome; import static only |
| D-06 | CI as a required job of build-deploy; e2e and actionlint jobs in CI | actionlint |
| D-07 | Fail-closed dev CIDR; policy check in validate.sh | Policy fails on regression |
| D-09 / D-14 (new) | All actions SHA-pinned; Bicep pinned with checksum; trivy tag fixed | actionlint |

Still open: everything that needs Azure or people (PRODUCTION_READINESS_PLAN Phases 0, 3–5).
