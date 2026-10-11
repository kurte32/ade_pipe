# Audit risk register (prioritised)

Findings ranked by actual risk. Likelihood and impact are for the production target described in the
architecture. Urgency: **P0** = before any production claim · **P1** = before a production rollout ·
**P2** = next hardening cycle · **P3** = backlog. Audit-finding rows are also mirrored into
`architecture/RISK_REGISTER.md`. Remediation status is maintained in `REMEDIATION_PLAN.md`.

| ID | Risk | Sev | Likelihood | Impact | Urgency |
|---|---|---|---|---|---|
| B-01 | Concurrent writes with the same ETag all commit → silent lost update and duplicate rows in the immutable ledger | Critical | High (two devices, offline replay, racing admin actions) | Data loss; corrupted audit trail | P0 |
| D-01 | `.env.example` untracked → clean clone and CI backend job fail | High | Certain on a fresh clone | Onboarding and CI broken; false “clean clone” claim | P0 |
| E-1 | Transient 5xx permanently halts a coordinator's offline sync chain; no auto-retry; under-surfaced | High | High (every deploy/scale/failover produces 5xx) | Coordinator work stuck until manual per-site retry | P1 |
| D-02 | Migrate job's KV secret bound to an identity with no vault access | Medium | Certain on first deploy | Every environment's deploy fails at migration | P1 |
| D-03 | Traffic shifts to the new revision before migrations run (ADR-010 violation) | Medium | High during any schema change | New code serves an un-migrated schema; failed migration leaves bad revision live | P1 |
| D-04 | "Build once, promote" not wired across per-env registries; dev-compiled SPA promoted | Medium | Certain on test/prod deploy | Test/prod pull a missing image / serve dev-tenant SPA | P1 |
| D-05 | Promotion chain skipped on release tags/dispatch | Medium | Certain on the documented prod path | Test and prod deploy nothing | P1 |
| D-06 | Deployment not gated on CI | Medium | Medium | Untested code can deploy to dev | P1 |
| B-02 | Idempotency doesn't dedupe concurrent submissions; losers get 500 | Medium | Medium (offline retry races, two tabs) | Opaque failure though the write succeeded | P1 |
| B-03 | `delta?conocidos=` 500s past ~2100 known ids | Medium | High at national scale | Offline sync permanently broken for large caches | P1 |
| B-04 | Bulk-load parses the whole sheet before the row limit | Medium | Medium (admin-authenticated) | Per-request CPU/memory exhaustion | P2 |
| B-05 | Upload part body fully buffered before the size check; no body limit | Medium | Medium (authenticated) | Memory-exhaustion vector | P2 |
| B-06 | Job batch deletes staging blob then can roll back its DB row | Medium | Low-Medium (needs a mid-batch failure) | Unrecoverable upload or orphan blob | P2 |
| A1 | Production guard doesn't validate the JWKS URL | Medium | Low (misconfig/tamper) | Wrong trust root accepted at start-up | P1 |
| D-07 | dev.bicepparam ships `0.0.0.0/0` ingress + DEBUG | Medium | Medium (if dev is deployed as-is) | Public dev API, verbose errors | P2 |
| C6 | List assertions coupled to row count; break as the DB grows | Medium | High (within a few CI runs) | CI goes red spuriously | P1 |
| C4 | Test ordering coupling; fails in isolation/sharding | Medium | Medium | CI flakiness, false failures | P2 |
| A5 / D-12 | Client-controlled XFF + correlation id written to the immutable ledger | Low | High (trivial to send) | Forensic trail poisoned | P2 |
| A2 | Unknown role string reaches the DB session context | Low | Low (needs a future un-gated route) | Potential RLS bypass | P2 |
| B-07 | Claimed `coordinador_oid` trigger absent | Low | Low | Child-table RLS could diverge from parent | P2 |
| C7 | No e2e teardown; dev DB grows every run | Low | High | Feeds C6; shared-state coupling | P2 |
| C8 | Coverage holes in production-only paths (promote/scan/graph/directory) | Low | — | Untested malware-scan promote/reject logic | P2 |
| C9 | Outbox retry test under-asserts | Low | — | Missed confidentiality regression | P3 |
| D-08 | `SCAN_MODE` hardcoded regardless of the Defender toggle | Low | Low | Uploads stall if the toggle is ever false | P2 |
| D-09 | Actions pinned to floating tags | Low | Low | Supply-chain exposure | P2 |
| D-10 / D-11 | Docs assert controls not implemented; several inaccuracies | Low | — | Operator confusion | P2 |
| E-2 | Raw "HTTP 500 (500)" shown to field users | Low | High | Confusing, non-actionable error | P3 |
| E-3 | Devolver disabled with no explanation | Low | Medium | Minor admin confusion | P3 |
| E-4 | Checkbox label overlaps the Filtrar button | Low | — | Cosmetic | P3 |
| B-08 | `assert` for a state invariant; `prev=None` edge → 500 | Info | Low | Narrow 500 window | P3 |
| C10 | No JWT algorithm-confusion test | Info | — | Missing regression (control exists) | P2 |
| C11 | Playwright `flows` project matches nothing | Info | — | Flows never run on desktop | P3 |
| E-5 | Site count 14 vs 13 | Info | — | Minor display off-by-one | P3 |
| E-6 | Shared dev DB accumulates e2e rows | Info | — | See C7 | P3 |

## Remediation status (2026-10-10)

**Fixed and verified this session:** B-01, D-01, E-1, A1, A2, B-03, C6, C10, C11 (code + regression
tests, clean-state verification). **Fixed statically only (no Azure):** D-02, D-05, D-08.
**Fixed (docs):** D-10, D-11, B-07. **Still open:** D-03, D-04, D-06, D-07, B-02, B-04, B-05, B-06,
A5/D-12, C4, C5, C7, C8, C9, and the E-/Info UX items. See `REMEDIATION_PLAN.md` for the full table.

## Remediation status (2026-10-11)

All code and pipeline findings are now fixed: locally verified for code, statically validated for
infrastructure and workflows. New findings A7, D-13 and D-14 were found and fixed. The remaining risk
is concentrated in what has never run: the deploy pipeline and every Azure-only control. Those are
tracked as Phases 3–5 of `PRODUCTION_READINESS_PLAN.md`.
