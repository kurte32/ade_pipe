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

To be filled in as fixes are applied in this session (findings are committed first, fixes in separate
commits).
