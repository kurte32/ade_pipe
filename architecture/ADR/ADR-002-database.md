# ADR-002: Transactional database

**Status:** Proposed  **Date:** 2026-10-10  **Deciders:** Subdirección de IA, Seguridad, TI

## Context and problem statement

The pipeline needs a transactional store for sites, status history, contact data, upload metadata, bulk-load staging, and audit, with per-coordinator isolation enforced inside the database (TDD 5.2, layer 3) and a read-only replica in Fabric for analytics and the future AI agent (TDD 4.2). TDD v0.1 chose Azure SQL Database; this ADR records why and what was compared.

## Requirements and constraints

- Fact (TDD RNF-01, 5.2): isolation by coordinador at API, service, and database. Database layer uses Row-Level Security with filter and block predicates driven by a session context set per connection.
- Fact (TDD 7.2): optimistic concurrency with `rowversion` exposed as ETag and `If-Match`.
- Fact (TDD RF-10, RNF-07): immutable log of status changes, loads, downloads, and returns.
- Fact (TDD 4.2, 17.1): data replicated to Fabric by Mirroring; the business confirmed Fabric capacity and the two tenant settings.
- Fact (verified in Learn): Mirroring of Azure SQL Database behind a private endpoint needs a VNet data gateway or on-premises data gateway.
- Fact (TDD 13): migrations with Alembic.
- Assumption: volume stays in the low thousands of sites for years; no need for horizontal partitioning.
- Constraint: owner contact data is personal data (TDD 5.3); the replica must be able to exclude it.

## Options considered

### Option A: Azure SQL Database (General Purpose, zone-redundant)

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | Moderate fixed cost; serverless tier for dev |
| Security | RLS, ledger tables, Entra authentication, TDE, private endpoint |
| Reliability | Zone redundancy, automated backups, point-in-time restore, long-term retention |
| Team familiarity | High (SQL Server lineage) |

Pros: RLS with `SESSION_CONTEXT`, `rowversion`, ledger tables for the audit requirement (ADR-009), native Fabric Mirroring, Entra-only authentication with a contained user for the managed identity.
Cons: licensing-based pricing is higher than PostgreSQL at equal compute; T-SQL specifics in migrations.

### Option B: Azure Database for PostgreSQL Flexible Server

| Dimension | Assessment |
|---|---|
| Complexity | Low to medium |
| Cost | Lower compute price |
| Security | RLS policies, Entra authentication, private endpoint |
| Reliability | Zone-redundant HA, backups |
| Team familiarity | Medium |

Pros: cheaper compute; PostgreSQL RLS is mature; SQLAlchemy support is excellent.
Cons: no native ledger tables (append-only must be emulated with permissions and triggers); Fabric Mirroring for PostgreSQL exists but its maturity, gateway support, and table selection must be checked (verify); `rowversion` must be emulated with a trigger-maintained version column; the team would build the session-context pattern from scratch.

### Option C: Azure Cosmos DB

| Dimension | Assessment |
|---|---|
| Complexity | Medium to high |
| Cost | Low at this volume but RU modelling is required |
| Security | Entra RBAC, private endpoint |
| Reliability | High |
| Team familiarity | Low |

Pros: elastic, global.
Cons: no row-level security in the SQL sense; multi-document transactions limited to a partition; relational model with history, staging, and catalogs maps poorly; Mirroring is available but the isolation requirement is unmet at the database layer.

## Decision and rationale

Option A. The combination the TDD depends on (RLS driven by session context, `rowversion`, Fabric Mirroring with table selection, and ledger tables for audit immutability) is native in Azure SQL and either partial or emulated elsewhere. The cost difference versus PostgreSQL is not decisive at one small database.

## Advantages and disadvantages

Advantages: the database enforces the third isolation layer independently of application code; audit immutability is a platform feature; the Fabric replica needs no pipeline code; backups and restore are managed.
Disadvantages: higher unit cost; the RLS predicate must be extended to child tables, which TDD v0.1 omitted; Mirroring bypasses RLS, so table selection is a security control that must be tested.

## Security, reliability, and cost implications

Security: Entra-only authentication, public network access disabled, private endpoint (ADR-008). Application identity is a contained user with `SELECT`, `INSERT`, `UPDATE` on business tables, `INSERT` and `SELECT` only on ledger tables, and no rights to alter security policies. `SESSION_CONTEXT` is set on connection checkout and cleared on checkin; `@read_only = 1` is not used because pooled connections are reassigned. `sitio_contacto`, `auditoria`, `operacion_idempotente`, and `carga_fila_staging` are excluded from Mirroring.
Reliability: zone-redundant General Purpose in prod and test; point-in-time restore; long-term retention aligned with the five-year document retention (Assumption pending TDD pendiente 12 for RPO and RTO).
Cost: moderate fixed cost in prod and test; serverless auto-pause in dev.

## Consequences and risks

- Child tables gain a denormalized `coordinador_oid` so the RLS predicate stays cheap and testable.
- An Admin bypass predicate (`SESSION_CONTEXT('rol') = 'Admin'`) must exist and be covered by the cross-access test suite.
- The VNet data gateway for Mirroring is an extra component with its own patching (ADR-008).
- Risk: a reassignment leaves stale data on the old coordinator's phone until the next delta sync; the delta endpoint must report removed sites.

## Conditions that would justify revisiting

- Fabric Mirroring for PostgreSQL reaches parity on table selection and private connectivity and the cost gap matters.
- A requirement for multi-region active writes appears.
- Licensing or cost policy forces open-source engines.

## Action items

- [ ] Write the RLS security policy with filter and block predicates for `sitio` and child tables, including the Admin bypass.
- [ ] Implement SQLAlchemy pool `checkout` and `checkin` hooks for `sp_set_session_context`.
- [ ] Define the contained database user for the managed identity with least privilege.
- [ ] Configure Mirroring with the excluded-table list and verify in Fabric that excluded tables are absent (Phase 0 spike 3).
- [ ] Decide backup retention once RPO and RTO are set (TDD pendiente 12).
