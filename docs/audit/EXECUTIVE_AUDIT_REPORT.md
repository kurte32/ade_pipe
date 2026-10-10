# Executive audit report — Pipeline de Posibles Tiendas

Date: 2026-10-10. Scope: the full implementation on branch `implementation` — FastAPI backend,
coordinator PWA and admin web, SQL Server / Azure SQL schema with Row-Level Security and ledger
audit, Azurite/Blob storage, Bicep infrastructure, and GitHub Actions. Method: independent,
adversarial review by five parallel streams (identity/authorization/RLS, business logic and data
integrity, test quality, infrastructure/CI-CD/docs, and a real-browser UX pass), each verifying
against the source requirements (the TDD and the Entra integration guide) and the approved
architecture rather than against the project's own status reports. Every confirmed defect was
reproduced against the running local stack or in Chrome; Azure-runtime items are flagged as not
verifiable without a subscription.

## Overall assessment

The system is **well-engineered and largely functional locally, but not production-ready.** The
security boundary is genuinely strong, the local developer experience works, and the test suite is
substantive rather than decorative. The audit nonetheless found one critical data-integrity defect,
a broken deployment path, and a core offline promise that degrades under the exact failure mode the
production topology produces. None of these is cosmetic.

What is solid, and independently verified:
- **Authentication and authorization hold up under attack.** Across all 33 API operations, no route
  returns success without a valid token; forged tokens (expired, wrong audience/issuer/azp, `alg:none`,
  and an RSA-public-key-as-HMAC-secret confusion attack) all return 401; the no-role user is refused
  everywhere; and one coordinator reading another's site gets 404, not a leak. No unhandled 500s
  across dozens of malformed-input probes.
- **Row-Level Security is fail-closed.** As the least-privilege application login with no session
  context, the seven protected tables return zero rows; with a coordinator's context, exactly their
  rows. The append-only audit and status-history ledgers reject UPDATE and DELETE at the database.
- **The tests are load-bearing.** The 125 backend tests run against real dependencies and would fail
  if their controls were removed; the 20 frontend unit tests and 14 Playwright end-to-end tests pass.

> **Remediation in the same session:** the Critical finding and both High findings were fixed and
> verified from a clean state (B-01, D-01, E-1), along with several Mediums (A1, A2, B-03, C6) and
> the quick deploy-path statics (D-02, D-05, D-08). See `REMEDIATION_PLAN.md` for the status table
> and verification protocol. The findings below describe the defects as found; each now carries its
> remediation status. The production-readiness verdict still stands, for the reasons in its section.

## Major findings

1. **Critical — silent lost update (B-01). [Fixed and verified.]** Optimistic concurrency was checked
   in Python before the UPDATE rather than in the UPDATE itself, so concurrent writes carrying the
   same ETag all succeeded. Reproduced twice: ten simultaneous transitions with one ETag all returned
   success and wrote ten duplicate rows into the append-only audit ledger. Two devices, a retried
   offline operation, or two admin actions racing would silently overwrite each other. The fix
   enforces the rowversion in the UPDATE (SQLAlchemy `version_id_col`); the burst now returns one
   success and the rest 412, and a deterministic regression test guards it. The admin return, discard,
   and reassign routes were confirmed to update the site row through the same mapper.
2. **High — a clean clone cannot be set up (D-01).** The `.env.example` the documentation tells every
   user to copy is not tracked by git, so a fresh clone fails at the first step and the CI backend job
   cannot load its environment. The “verified from a clean clone” claim does not hold.
3. **High — offline sync wedges on transient server errors (E-1).** A 5xx response — which the Front
   Door and Container Apps topology produces on deploys, scale events, and failovers — marks a queued
   change as a permanent error and halts that site's whole sync chain with no automatic retry. No data
   is lost, but recovery requires the coordinator to find and retry each affected site by hand, and the
   site list gives no signal that anything is stuck.
4. **Medium cluster — the deployment path cannot work as written (D-02 to D-06).** The migration job
   references a secret its identity cannot read; traffic shifts to the new revision before migrations
   run, against the approved ADR; “build once, promote” is not wired across the per-environment
   registries; the promotion chain is skipped on release tags so only dev ever deploys; and deployment
   is not gated on CI. Each independently prevents a working dev→test→prod deployment.
5. **Medium — reliability and input-handling defects (B-02 to B-06).** Idempotency does not deduplicate
   concurrent submissions (losers get 500); delta sync 500s once a device knows more than ~2100 sites;
   bulk-load and upload size limits are enforced only after the full body is in memory; and a
   background-job batch can delete a staging blob and then roll back its own database row.

## Production-readiness verdict

**Not production-ready.** The Critical finding (B-01) and both High findings (D-01, E-1) are now fixed
and verified locally, so the original gating item is cleared. The verdict stands for two independent
reasons. First, nothing has been validated in Azure — Entra sign-in, Graph, Teams, Defender,
immutability, Private Link, and the whole deploy pipeline are written and at most statically validated.
Second, the deploy path is only partly corrected: D-02, D-05, and D-08 are fixed on inspection, but
D-03 (migration ordering), D-04 (build-once promotion), and D-06 (no CI gate) remain open and each
prevents a correct dev→test→prod deployment. The security posture and the local build quality are
strong. Once the remaining deploy-path items are done and the pipeline is exercised in a real test
subscription, the system is a credible candidate for a staged production rollout.

See `TECHNICAL_FINDINGS.md` for every finding with evidence, `SECURITY_ASSESSMENT.md`,
`TEST_VALIDATION_REPORT.md`, `RISK_REGISTER.md` (prioritised), `REMEDIATION_PLAN.md`, and
`DOCUMENTATION_CORRECTIONS.md`. Remediation status after this audit is recorded at the top of the
remediation plan.
