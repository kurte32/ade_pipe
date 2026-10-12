# Architecture documentation · Pipeline de Posibles Tiendas

Planning artifacts produced on 10 October 2026 from TDD v0.1, the Entra ID integration guide, and the design review `../Propuesta_mejoras_TDD_v0.1.md`. They defined the path to the platform that now exists in this repository; `AS_IS.md` records the state before implementation, and `../docs/RELEASE_READINESS.md` the current verified state.

| Document | Purpose |
|---|---|
| `AS_IS.md` | Verified current state: what exists in the repository, implementation status per capability, gaps in the documented design, open items |
| `TO_BE.md` | Target architecture: style, components, data, critical flows with diagrams, assumptions, open questions |
| `AZURE_DESIGN.md` | Azure service selection, deployment topology, network boundaries, identity model, environments, cost posture |
| `SECURITY.md` | Trust boundaries, threat model, controls by area, mobile security, compliance, outstanding risks |
| `ADR/` | Ten Architecture Decision Records, ADR-001 to ADR-010 |
| `IMPLEMENTATION_PLAN.md` | Six phases with tasks, deliverables, acceptance criteria, dependencies, effort ranges |
| `RISK_REGISTER.md` | Prioritized risks with probability, impact, mitigation, owner, residual exposure |
| `PRODUCTION_READINESS.md` | Operational requirements, observability, resilience, backup, runbooks, production acceptance gates |

Labels used in every document: **Fact** (from the TDD, the guide, or verified in Microsoft Learn during this exercise), **Assumption** (default adopted so planning can proceed, listed in `TO_BE.md` section 9), **Recommendation** (change over TDD v0.1), **Open** (needs an owner's answer).

Phase numbering: this set uses Phase 0 (spikes) to Phase 5 (hardening and go-live). The earlier review `../Propuesta_mejoras_TDD_v0.1.md` refers to the TDD's own phases 1 to 4 (TDD section 15.1); its "fase 2" and "fase 3" correspond to Phase 3 and Phase 4 here.

Language: English, with Spanish domain terms kept verbatim (Sitio Prospectado, Dueño Localizado, Primera visita, Recepción de documentos, carga, devolución, coordinador, administrador).

Decision map:

| ADR | Decision |
|---|---|
| ADR-001 | Compute: Azure Container Apps with Jobs for background work |
| ADR-002 | Database: Azure SQL Database with RLS and ledger tables |
| ADR-003 | Documents: flat Blob staging with Defender scanning, ADLS Gen2 definitive store, OneLake shortcut |
| ADR-004 | Two SPAs in a monorepo on Static Web Apps behind Front Door |
| ADR-005 | Offline synchronization semantics and client storage decisions |
| ADR-006 | Token validation, client restrictions, role assignment |
| ADR-007 | Teams notification mechanism with outbox |
| ADR-008 | Network posture with private endpoints, secrets with managed identity and Key Vault |
| ADR-009 | Audit immutability with ledger tables and INSERT-only grants |
| ADR-010 | Bicep and GitHub Actions for IaC and CI/CD |
