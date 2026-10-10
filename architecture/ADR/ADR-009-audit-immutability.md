# ADR-009: Audit trail immutability

**Status:** Proposed  **Date:** 2026-10-10  **Deciders:** Subdirección de IA, Seguridad, Legal (retention), TI

## Context and problem statement

TDD v0.1 requires an immutable log of status changes, cargas, document downloads, and devoluciones (RF-10, RNF-07) and models `auditoria` and `sitio_estatus_historial` as "solo inserción". That is a convention in application code: the database account could still update or delete rows, and nothing proves rows were not altered. This ADR decides how immutability is enforced and evidenced.

## Requirements and constraints

- Fact (TDD RF-10): immutable record of status changes, loads, downloads, and returns.
- Fact (TDD RNF-07): every write and every download leaves user, date, and origin.
- Fact (TDD 5.3): logs contain no contact data or file content.
- Fact (TDD HU-18): penetration and RLS tests before production; auditors will ask how the log is protected.
- Fact (ADR-002): Azure SQL Database is the store, which offers ledger tables.
- Assumption: the log must be queryable by the administrator (HU-15) from the same database.
- Constraint: the application identity must keep inserting under RLS without `db_owner`.

## Options considered

### Option A: Append-only ledger tables plus INSERT-only grants for the application identity

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | None beyond ledger storage overhead (verify) |
| Security | Tamper evidence by cryptographic digest; updates and deletes rejected by the engine |
| Reliability | Native; digests can be stored in immutable Blob storage for verification (verify) |
| Team familiarity | Medium |

Pros: enforcement and evidence in the platform; no application code; auditors get a verifiable digest.
Cons: schema changes on ledger tables are restricted (verify which operations are allowed); Alembic migrations must account for that.

### Option B: Permissions only (no `UPDATE` or `DELETE` grants) with a convention in code

| Dimension | Assessment |
|---|---|
| Complexity | Lowest |
| Cost | None |
| Security | Stops the application identity, not a privileged operator |
| Reliability | Good |
| Team familiarity | High |

Pros: trivial.
Cons: no evidence of integrity; a `db_owner` can rewrite history silently.

### Option C: Ship audit events to an external SIEM or Log Analytics with retention lock, keep SQL mutable

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Cost | Ingestion and retention |
| Security | Immutable copy outside the database |
| Reliability | Two sources that can diverge |
| Team familiarity | Medium |

Pros: central security monitoring.
Cons: HU-15 queries the database; divergence between copies; retention costs for five years of logs.

## Decision and rationale

Option A for `auditoria` and `sitio_estatus_historial`, combined with Option B's grants as a second layer. Ledger tables make the requirement a property of the database rather than of the code and give auditors a digest to verify. Option C is not adopted for the authoritative log but security-relevant events (authentication failures, 403s, RLS test results) still flow to Application Insights for monitoring (PRODUCTION_READINESS).

## Advantages and disadvantages

Advantages: `UPDATE` and `DELETE` are rejected by the engine on append-only ledger tables; a periodic digest proves the log is intact; no changes to the API beyond inserting rows.
Disadvantages: ledger tables constrain some schema evolution, so audit row shape must be designed with a flexible `detalle` column; digest storage adds a small operational task.

## Security, reliability, and cost implications

Security: the application identity has `INSERT` and `SELECT` on both tables and nothing else; security policy objects are owned by a separate deployment identity used by migrations; ledger digests are published to an immutable container in the documents storage account (ADR-003) on a schedule.
Reliability: ledger does not affect write latency materially at this volume (verify); restore procedures must include digest verification.
Cost: storage overhead of ledger history (verify); no new services.

## Consequences and risks

- Alembic migrations create these tables with ledger options and treat them as add-only; the migration identity differs from the runtime identity.
- Risk: a later need to purge personal data from audit rows (TDD pendiente 7) conflicts with append-only; audit rows therefore carry identifiers and reason codes, never free-text personal data, which TDD 5.3 already requires.
- Risk: mirrored copies of these tables in Fabric would not be ledger-protected; they are excluded from Mirroring (ADR-002).

## Conditions that would justify revisiting

- The database moves off Azure SQL (ADR-002 revisited).
- Legal requires deletion of specific audit rows, which append-only cannot satisfy.
- A corporate SIEM becomes the mandated system of record for audit.

## Action items

- [ ] Define `auditoria` and `sitio_estatus_historial` as append-only ledger tables in the initial migration.
- [ ] Grant `INSERT` and `SELECT` only to the application identity; test that `UPDATE` and `DELETE` fail.
- [ ] Schedule digest generation and storage in an immutable container; document the verification procedure.
- [ ] Confirm ledger schema-change restrictions and migration approach (verify).
