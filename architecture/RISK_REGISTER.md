# Risk Register · Pipeline de Posibles Tiendas

Status: Proposed, 10 October 2026. Companion to `TO_BE.md`, `AZURE_DESIGN.md` and `SECURITY.md`. Scoring: Probability and Impact on L=1, M=2, H=3; Score is the product (1 to 9). Owners are roles, not people. ADR numbers follow `AZURE_DESIGN.md` section 1. Items marked (verify) rest on platform behavior not confirmed in this exercise.

## 1. Prioritized register

| ID | Risk | Category | P | I | Score | Mitigation | Owner role | Residual | Status |
|---|---|---|---|---|---|---|---|---|---|
| R01 | Offline model contradiction: MSAL `sessionStorage` and token expiry prevent the PWA from opening without signal, so field work stops | Gap to target | H | H | 9 | Adopt "open without token, sync with token" (`TO_BE.md` 6.1); `localStorage` cache ratified by Seguridad; Phase 0 spike on a managed Android | Arquitectura, Seguridad | L after spike | Open |
| R02 | `loginRedirect` from an installed PWA returns to a browser tab and loses state (verify) | Operational | M | H | 6 | Phase 0 spike; fallback is running the PWA in Edge without installing; exclude Entra redirect paths from the service worker navigation fallback | Frontend lead | L after spike | Open |
| R03 | Fabric shortcut to `st-doc` not possible with public access disabled in this tenant (Open 3) | External dependency | M | H | 6 | Phase 0 spike with trusted workspace access; fallback is resource-instance rule or, last resort, direct OneLake write (TDD v0.1 path) kept as ADR-003 alternative | TI, Fabric admin | M until spike | Open |
| R04 | Backend compromise sets arbitrary `SESSION_CONTEXT`, bypassing RLS (Fact, TDD 5.2) | Security | L | H | 3 | Managed identity, SQL user without policy rights, image scanning, Defender for Containers, anomaly alerts, ledger audit | Seguridad | M, accepted | Accepted |
| R05 | Fabric mirror contains owner personal data visible to analysts | Security | H | M | 6 | Exclude `sitio_contacto`, `auditoria`, `operacion_idempotente`, `carga_fila_staging` from Mirroring; Fabric workspace roles (S7) | Datos, Seguridad | L | Open |
| R06 | RLS predicate gaps on child tables (`sitio_contacto`, `sitio_visita`, `sitio_archivo`) leak data through joins or direct reads | Security | M | H | 6 | Denormalized `coordinador_oid` with trigger check; predicates on every child table; CI test suite per table (`SECURITY.md` 8) | Backend lead | L | Open |
| R07 | Audit and history tables are append-only by convention and can be edited | Security | M | M | 4 | Ledger tables plus INSERT-only grants (ADR-009); CI test that UPDATE and DELETE fail | Backend lead, DBA | L | Open |
| R08 | 24-hour SPA refresh token lifetime (guide, verify tenant policy) forces interactive sign-in after a day without signal, risking loss of queued work | Operational | H | M | 6 | Queue persists independently of token state; clear "sign in to sync" state; Phase 0 test of renewal after 24 h offline | Frontend lead, Identidad | L | Open |
| R09 | Defender for Storage on-upload scanning unavailable, not approved, or slow in the tenant (verify) | External dependency | M | M | 4 | Phase 0 spike; files stay in staging until a result arrives; alert when a session waits longer than a threshold; fallback is an open-source scanner job (adds a component) | Seguridad, TI | M until spike | Open |
| R10 | Mirroring through a VNet data gateway adds a component, a subnet and an operations burden that nobody owns | Operational | M | M | 4 | Decide ADR-008 early; if private endpoints are a preference, use service firewalls and drop the gateway; otherwise assign gateway ownership to TI | TI | M | Open |
| R11 | Bulk reload overwrites coordinator progress or reassigns advanced sites | Data loss | M | H | 6 | Upsert by `origen_id` never touches status or captured data; changed `USUARIO`, `REGIÓN`, `SITIO` on existing rows become warnings requiring admin decision; load tests with the sample file (Fact, TDD 8.4) | Backend lead | L | Open |
| R12 | GPS column meaning undefined (zeros, blanks, values in the thousands) leads to wrong use downstream | Data integrity | H | L | 3 | Store as text, never interpret; document as pending (TDD pendiente 2); exclude from any validation | Negocio | L | Open |
| R13 | Teams notification mechanism unapproved: Office 365 connectors are retired (Fact, verified), activity feed needs a Teams app and admin consent | External dependency | M | M | 4 | In-app notice is the baseline from Phase 3; outbox decouples delivery; ADR-007 chooses Graph activity feed with Power Automate fallback; request approval in Phase 0 | TI, Seguridad | L | Open |
| R14 | Entra ID P1 not available, so app roles cannot be assigned to groups (verify) | External dependency | L | M | 2 | Direct user-to-role assignment, acceptable at ten users; document the maintenance owner | Identidad | L | Open |
| R15 | Single-region outage takes the platform down; no RTO stated (TDD pendiente 12) | SPOF | L | M | 2 | Zone-redundant SQL and Container Apps, geo-redundant backups and storage, documented manual restore; multi-region only if an RTO under hours is required (`TO_BE.md` 8) | TI, Negocio | M, accepted until RTO defined | Open |
| R16 | Front Door or Container Apps timeouts interrupt 150 MB downloads over 4G (verify) | Operational | M | M | 4 | `Range` support on `/archivos/{id}`; verify both timeouts in Phase 0; fallback is short-lived user-delegation SAS for the admin web only | Backend lead | L after verification | Open |
| R17 | IndexedDB quota or eviction on phones loses queued photos | Data loss | M | M | 4 | PDFs online-only (Assumption 2); client-side compression; per-site photo cap; persistent storage request; photos deleted only after server confirmation | Frontend lead | L | Open |
| R18 | Private networking (Front Door Premium, dedicated workload profile, gateway, private endpoints) sets a cost floor disproportionate to ten users | Cost | H | M | 6 | ADR-008 decision with Seguridad; service-firewall variant documented; dev scales to zero; test paused outside UAT | Arquitectura, TI | M | Open |
| R19 | No team, estimates, or CI/CD platform defined (TDD pendiente 12), so the roadmap cannot be committed | Migration and deployment | H | M | 6 | Assumption 5 (GitHub Actions, Bicep) as default; estimates as ranges; revisit at Phase 1 start | Subdirección de IA, TI | M | Open |
| R20 | No git repository or monorepo exists; the only artifacts are PDFs and markdown | Tech debt | H | L | 3 | Phase 1 first task: `git init`, monorepo skeleton, protected `main`, CI scaffold | Arquitectura | L | Open |
| R21 | Penetration test findings arrive late and block go-live | Migration and deployment | M | M | 4 | Book the pen test at Phase 1 start; run automated security tests from Phase 1; Defender for Cloud recommendations gate monthly | Seguridad | L | Open |
| R22 | Legal pendientes unresolved: retention start event, legal hold, discarded-site data, privacy notice (TDD pendientes 7 and 13) | External dependency | M | M | 4 | Immutability policy parameterized so the start event is configuration; privacy notice screen built with placeholder text behind a feature flag; escalate to Legal by Phase 2 | Legal | M | Open |
| R23 | Status machine has no terminal or negative state, so non-viable sites accumulate as active work | Gap to target | H | L | 3 | Add `Descartado` and `Entregado` with reason catalog (Open 5); `estatus` catalog with terminal flag | Negocio, Backend lead | L | Open |
| R24 | Offline chain replay rejected as a false conflict when a contact edit precedes a transition | Data integrity | H | M | 6 | Per-site FIFO, chained ETag, `Idempotency-Key` store (`TO_BE.md` 6.2, ADR-005); Playwright offline tests | Frontend lead, Backend lead | L | Open |
| R25 | Shared phones between coordinators expose one coordinator's cache to another (Open 6) | Security | L | M | 2 | Ask Negocio; if shared, sign-out on close and per-user cache namespace | Negocio, Seguridad | L | Open |

## 2. Top 5 with detail

**R01 · Offline model contradiction (score 9).**
Probability high: the guide and the TDD currently point in opposite directions, and nothing has been tested on a device. Impact high: without it, the core promise of RNF-02 fails and coordinators revert to paper. Mitigation: formalize the two-state model in the TDD and in `packages/auth`; `localStorage` under Intune app protection; Phase 0 spike with written exit criteria. Residual low once the spike passes. Escalation trigger: the spike shows Edge app protection does not cover site storage, or Seguridad rejects `localStorage`; then the fallback is a shorter offline window with forced daily sign-in, and the business must accept it.

**R03 · Fabric shortcut blocked by network posture (score 6).**
Probability medium: trusted workspace access exists as a feature, but tenant configuration and the private-endpoint mandate interact. Impact high: it decides the whole document path (ADR-003) and the retention design. Mitigation: Phase 0 spike before any storage code; keep the TDD v0.1 OneLake path as the documented alternative. Residual medium until the spike runs. Escalation trigger: the spike fails after both trusted workspace access and resource-instance rules are tried; then ADR-003 is reopened and Phase 4 scope changes.

**R18 · Private networking cost floor (score 6).**
Probability high: the design as assumed includes every private-networking component. Impact medium: cost rather than function, but it can stall approval. Mitigation: ADR-008 asks Seguridad a single question, mandate or preference; the service-firewall variant is fully documented and removes the VNet, the gateway and Front Door Private Link. Residual medium because corporate standards may still require it. Escalation trigger: monthly cost estimate exceeds the budget TI approves for a ten-user system.

**R24 · False conflicts on offline replay (score 6).**
Probability high: the TDD specifies `If-Match` and idempotency without replay ordering, so a naive implementation will hit it in the first field test. Impact medium: coordinators see spurious errors and lose trust in sync. Mitigation: ADR-005 semantics, `operacion_idempotente` table, chained ETags, Playwright tests with network emulation. Residual low. Escalation trigger: UAT reports more than occasional conflict messages not caused by an admin return.

**R06 · RLS gaps on child tables (score 6).**
Probability medium: the TDD describes RLS on `sitio` "and its child tables" but no child table carries the owner column. Impact high: cross-coordinator disclosure of owner contact data. Mitigation: denormalize `coordinador_oid`, predicates per table, trigger check, per-table CI tests. Residual low. Escalation trigger: any CI cross-access test failure after Phase 1, or a pen test finding in this area.

## 3. Risk review cadence

| Gate | When | Review scope |
|---|---|---|
| Phase 0 exit | After the three spikes | Close or re-score R01, R02, R03, R08, R09, R16; decide ADR-003 and ADR-008 |
| Phase 1 exit | Foundations deployed | R06, R07, R14, R18, R19, R20; pen test booked (R21) |
| Phase 2 and 3 exits | Admin load and coordinator flow in `test` | R11, R12, R17, R22, R23, R24, R25 |
| Phase 4 exit | Documents and returns complete | R05, R09, R13, R16 |
| Phase 5 exit, production readiness | Before go-live | All open risks re-scored; R04 and R15 formally accepted by Seguridad and Negocio; register attached to `PRODUCTION_READINESS.md` |
| Steady state | Monthly | New risks from incidents, Defender for Cloud recommendations, cost review |
