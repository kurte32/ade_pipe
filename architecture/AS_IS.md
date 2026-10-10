# Current State (AS-IS) · Pipeline de Posibles Tiendas

Status: Verified on 10 October 2026 against the contents of `/home/kurt/Documents/projects/ade_pipeline`.

## 1. Repository evidence

The project directory contains three files and no version control:

| File | Type | Content |
|---|---|---|
| `TDD_Pipeline_Tiendas_v0.1.pdf` | Design document, 15 pages, Spanish, dated 9 October 2026 | Technical design draft for review. Thirteen explicit pendientes. |
| `Guia_Integracion_Entra_ID_React_FastAPI.pdf` | Step-by-step guide, 19 pages, Spanish | Entra ID app registrations, MSAL React setup, FastAPI JWT validation, test plan. |
| `Propuesta_mejoras_TDD_v0.1.md` | Design review, 10 October 2026 | Proposed improvements that this architecture set adopts. |

Not present (Fact, verified by directory listing):

- No git repository, no commit history.
- No source code for the PWA, the admin web, or the API.
- No dependency manifests (`package.json`, `pyproject.toml`, `requirements.txt`).
- No infrastructure definitions (Bicep, Terraform, ARM).
- No database schema or migrations.
- No tests.
- No CI/CD workflows.
- No configuration files, environment templates, or secrets.
- No README.

The Phase One audit requested in the engagement brief therefore reduces to an audit of the two documents. Nothing can be validated against running code.

## 2. Implementation status by capability

Classification: Implemented, Partially implemented, Claimed but unverifiable, Planned, Assumption.

| Capability | TDD reference | Status | Evidence |
|---|---|---|---|
| Entra sign-in for coordinators and admins | RF-01, HU-01 | Planned | Guide Parts A and B describe the configuration; no registrations confirmed in a tenant |
| FastAPI JWT validation with roles | Guide Part C | Claimed but unverifiable | Guide section C5 reports nine test cases passed with locally signed tokens. The code is not in the repository and was never run against the tenant |
| Per-coordinator isolation at API, service, and DB (RLS) | RNF-01, 5.2, HU-02 | Planned | Design only |
| Site list, detail, status transitions with If-Match | RF-02, RF-03, 7, 12 | Planned | API table in TDD section 12 |
| Contact, measurements, photos capture | RF-04 | Planned | Minimum fields are pendiente 5 |
| Offline queue and sync | RNF-02, 10, HU-10 | Planned | Design only; MSAL cache choice conflicts with it (see `../Propuesta_mejoras_TDD_v0.1.md` A1) |
| Bulk load CSV/XLSX/XLS with preview and approval | RF-05, 8, HU-03 to HU-05 | Planned | Sample file `pipeline_nacional_mx_20261009.xlsx` is referenced in the TDD but is not in the repository |
| Resumable chunked PDF upload | RF-08, 9.2, HU-09, HU-11 | Planned | Design only; OneLake write path flagged as a risk by the TDD itself |
| Documents in Fabric with metadata | HU-16 | Planned | Fabric capacity and tenant settings confirmed by the business (TDD 17.1) |
| Admin return with reason and history | RF-06, HU-13 | Planned | Reason catalog is pendiente 8 |
| Teams notification on return | RF-07, 11, HU-14 | Planned, mechanism undefined | TDD marks it POR VALIDAR |
| Equivalence table user code to email to oid | RF-09 | Planned | oid resolution method not designed |
| Immutable audit log | RF-10, RNF-07, HU-15 | Planned | "Solo inserción" by convention only |
| Five-year retention and purge | RF-11, RNF-04, 9.3, HU-17 | Planned | Start event is pendiente 7 |
| IaC, CI/CD, environments | 13 | Planned | CI/CD platform is pendiente 12 |
| Telemetry and alerts | 13 | Planned | Application Insights named, no design |
| Pen test and RLS tests | 14, HU-18 | Planned | |
| Intune and Conditional Access compatibility | RNF-03, 5.4 | Assumption | Pendiente 10; no browser decided |

Summary: zero capabilities implemented, one claimed and unverifiable, all others planned.

## 3. Documented architecture (as designed in TDD v0.1)

- **Clients:** two React and TypeScript SPAs. Coordinator PWA (Vite, MSAL React, Workbox, Dexie) for Intune-managed Android. Admin web (MSAL React). Hosting for the SPAs is not specified.
- **API:** Python 3.12, FastAPI, SQLAlchemy, Alembic, pandas, openpyxl, xlrd, pypdf. Hosted on Azure Container Apps behind Front Door with WAF. Managed identity to all resources.
- **Data:** Azure SQL Database with Row-Level Security via `SESSION_CONTEXT`. Fabric Mirroring to a Lakehouse.
- **Files:** Blob Storage staging for chunked upload and validation; definitive files written to OneLake (Lakehouse Files) with the Data Lake SDK. Path `Files/pipeline/{sitio_id}/{tipo}/{archivo_id}_{sha256}.{ext}`.
- **Identity:** single-tenant Entra ID, three app registrations, app roles Coordinador and Admin assigned via groups, PKCE, MFA and managed-device Conditional Access.
- **Secrets and telemetry:** Key Vault, Application Insights, Log Analytics.
- **Notifications:** Microsoft Graph to Teams, mechanism to validate.
- **Data model:** eleven tables (TDD section 6). Status flow of four states with admin returns (section 7). Transition requirements modelled as a configuration table.
- **Testing strategy:** unit, integration with real DB and RLS, security (cross-access, role escalation, malicious files, formula injection, pen test), offline, load file, device, acceptance with coordinators.
- **Phases:** four phases plus "posterior" for the AI agent, without estimates.

## 4. Verified gaps and limitations of the documented design

From `../Propuesta_mejoras_TDD_v0.1.md`, grouped by severity. Each item cites the TDD or guide section.

High:

1. Offline-first requirement (TDD 10) contradicts the guide's `sessionStorage` MSAL cache (B3) and the 24-hour SPA refresh token (Part D). No defined behavior for opening the app without a valid token.
2. Definitive storage by writing to OneLake from an external backend is the TDD's own risk (16), leaves malware scanning as "por validar" (9.2), and provides no platform mechanism for the five-year retention or legal hold (9.3, pendiente 7).
3. Risk number one in the TDD, 150 MB PDFs captured offline, stems from a requirement RF-08 does not actually impose.
4. Offline replay semantics are undefined: a contact edit followed by a transition on the same site would be rejected by the `If-Match` check after the first operation changes the rowversion (7.2, 10, 12).
5. RLS is incomplete: child tables have no predicate column, Admin bypass is unspecified, pooled-connection handling is unspecified, and Fabric Mirroring bypasses RLS so `sitio_contacto` (owner personal data) would replicate to Fabric without an access design (5.2, 5.3, 6).

Medium:

6. The two-SPA rationale cites Conditional Access policies per client (4.3, guide 2). CA evaluates against the resource app; the correct lever is group targeting (verified in Microsoft Learn).
7. SPA hosting is absent from the component table (4.2).
8. Audit and history immutability is a code convention (6).
9. The state machine has no terminal or negative state, while pendiente 7 already refers to "cierre o descarte del sitio" (7).
10. Email-to-oid resolution for `coordinador_equivalencia` is not designed and the required Graph permission is not requested (6, 8.3, guide 8).
11. Teams incoming webhooks via Office 365 connectors are retired (verified); the TDD's options are not enumerated (11).
12. Private endpoints for SQL imply a VNet-integrated Container Apps environment and a VNet data gateway for Mirroring, neither of which appears in the TDD (5.3, 13).
13. Missing tables: idempotency store, upload session, notification outbox, status catalog, return reason catalog (6).

Low: formula-injection scope, Excel date typing under pandas, reload semantics for changed region or name, download timeouts for large files, npm dependency scanning in CI, original FECHA text retention.

## 5. Constraints inherited from the business (TDD 17.1, Fact)

Entra accounts for all coordinators; Fabric capacity and tenant settings confirmed; USUARIO is the regional coordinator and the business provides the equivalence table; admin may return status; admin decides doubtful rows; PDF up to 50 pages and 150 MB; five-year retention; two file types; Mexico City time; Android with Intune; Teams notifications; Legal approved contact data processing; CSV and Excel with pandas; GPS column loaded as-is.

## 6. Open items carried forward (TDD 17.2)

| # | Pendiente | Owner | Architectural impact |
|---|---|---|---|
| 1 | Equivalence table for the ten users | Negocio | None on design; needed for UAT |
| 2 | GPS column meaning | Negocio | None; stored uninterpreted |
| 3 | Reload mode and frequency | Negocio | Upsert rules in `cargas` |
| 4 | Catalog of the four required documents | Negocio | `catalogo_tipo_documento` seed |
| 5 | Minimum contact and measurement fields | Negocio | Transition rule parameters |
| 6 | Photo formats and size | Negocio, TI | Offline queue cap |
| 7 | Retention start event, legal hold, discarded sites | Legal | Immutability policy, terminal states |
| 8 | Return reason catalog | Negocio | `motivo_devolucion` seed |
| 9 | Load file size and row limits | TI | Upload limits, parsing in background |
| 10 | PWA compatibility with Intune and CA | Seguridad, Intune | Edge mandate, MSAL cache, Phase 0 spike |
| 11 | Teams mechanism and permissions | TI, Seguridad | ADR-007 |
| 12 | CI/CD platform, RPO and RTO | TI | ADR-010, backup tier |
| 13 | Privacy notice text | Legal | PWA screen |

## 7. Technical debt and risks already present

There is no code, so there is no code debt. The debt is documentary:

- The guide's FastAPI sample accepts both v1 and v2 issuers and does not check `scp`, `azp`, or `tid`.
- The guide's `acquireTokenRedirect` inside a `catch` block reproduces the redirect loop the same guide warns about (B5 versus B7).
- The sample load file and the "tested" FastAPI code are referenced but not stored with the design, so neither can be reproduced.
- Repository hygiene: no git, no README, no conventions. The first task of Phase 1 is `git init` with the monorepo scaffold (`IMPLEMENTATION_PLAN.md`).
