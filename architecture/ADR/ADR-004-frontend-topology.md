# ADR-004: Two SPAs in a monorepo, hosting, and the Conditional Access rationale

**Status:** Proposed  **Date:** 2026-10-10  **Deciders:** Subdirección de IA, Identidad, Seguridad

## Context and problem statement

TDD v0.1 (4.1, 4.3) specifies two separate React applications, a PWA for coordinadores and a web for administrators, each with its own Entra app registration, and justifies the split with "distinct Conditional Access policies for the administrator". The Entra guide (section 2) repeats that reason. The TDD does not say where the SPAs are hosted; only the API container has a home (4.2). This ADR settles the number of frontends, the hosting, and corrects the security rationale.

## Requirements and constraints

- Fact (TDD RNF-03, 5.4): coordinador app runs as a PWA on Intune-managed Android, offline-first.
- Fact (TDD RF-05 to RF-09): the administrator works with file uploads, previews, audit queries, and reassignments, a desktop workflow.
- Fact (verified in Learn): Conditional Access applies to the resource being accessed, not to public clients. Both SPAs request tokens for the same resource, `pipeline-api`, so a policy targeting the API applies to both. Differentiated requirements for administrators come from targeting the `PIPELINE-Admins` group.
- Fact (Entra guide A10): Assignment Required is set on `pipeline-api`.
- Assumption (TO_BE 9.4, 9.5): Front Door Premium is the single public host; GitHub Actions deploys.
- Constraint: one team maintains both frontends; shared code should be shared, not copied.

## Options considered

### Option A: Two apps in one pnpm monorepo with shared packages, hosted on two Static Web Apps behind Front Door

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Cost | Low (Static Web Apps Standard, two instances) |
| Security | Separate registrations, Assignment Required on the admin SPA, smaller PWA attack surface |
| Reliability | Static hosting, independent deploys |
| Team familiarity | High |

Pros: tailored UX and offline bundle for the PWA; independent release cadence; shared `api-client`, `auth`, `ui` packages prevent drift; preview environments per pull request.
Cons: two pipelines and two sets of redirect URIs; monorepo tooling to set up.

### Option B: One SPA with role-gated routes and one registration

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | Lowest |
| Security | Admin screens ship to every phone even if hidden; one registration |
| Reliability | One deploy affects both audiences |
| Team familiarity | High |

Pros: one codebase, one pipeline.
Cons: offline bundle includes admin code and dependencies (pandas-like grid, file preview); cannot set Assignment Required per audience; a bad admin release breaks field work.

### Option C: Two apps served by the API container as static files

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | None extra |
| Security | Same origin as API |
| Reliability | Frontend and API deploy together |
| Team familiarity | High |

Pros: no CORS by construction.
Cons: couples frontend releases to the API revision; container restarts on static changes; service worker caching interacts with API ingress; loses Static Web Apps preview environments.

## Decision and rationale

Option A. Keep two applications, but for the right reasons: different UX, a lean offline bundle, and independent release cadence. Conditional Access differentiation comes from group-targeted policies on `pipeline-api`, not from the SPA split. Add Assignment Required on `pipeline-web-admin` with only `PIPELINE-Admins` assigned so a coordinador cannot sign in to the admin web at all. Host both on Azure Static Web Apps routed by Front Door under one host (`/` for the PWA, `/admin` for the web, `/api/*` to Container Apps), which removes CORS in production and gives a single CSP and certificate.

## Advantages and disadvantages

Advantages: shared typed client enforces `Idempotency-Key` and `If-Match` conventions in one place; the PWA ships only what the field needs; admin changes never redeploy the PWA; one public hostname.
Disadvantages: monorepo setup cost; two Static Web Apps per environment; per-environment Entra registrations multiply (six SPA registrations across dev, test, prod).

## Security, reliability, and cost implications

Security: public clients hold no secrets; redirect URIs per environment under the Front Door host; Assignment Required on both the API and the admin SPA; CSP restricting script sources to self and Entra endpoints; the service worker excludes Entra redirect responses from caching.
Reliability: static hosting has no runtime to fail; Front Door health probes on each origin; a PWA release is rolled back by redeploying the previous build artifact.
Cost: Static Web Apps Standard for custom domains and private origins behind Front Door (verify private origin support); otherwise negligible.

## Consequences and risks

- TDD 4.3 and the Entra guide section 2 must be corrected in v0.2.
- The identity request message (guide section 8) gains: Assignment Required on `pipeline-web-admin`, group-targeted Conditional Access policies on `pipeline-api`.
- Risk: path-based routing (`/admin`) requires the admin SPA to be built with a base path; a sub-host (`admin.pipeline.{domain}`) is the fallback at the cost of CORS for that origin.
- Risk: `loginRedirect` inside an installed PWA on Android is a reported problem (verify in Phase 0); mitigations are in ADR-005.

## Conditions that would justify revisiting

- The admin role shrinks to a few screens with no file handling, making a single SPA cheaper to maintain.
- A third audience (supervisor, consulta) appears, at which point a role-gated shell with lazy-loaded modules may be better than a third app.
- Static Web Apps cannot sit behind Front Door with public access disabled and the organization requires that.

## Action items

- [ ] Scaffold the pnpm monorepo: `apps/pwa-coordinador`, `apps/web-admin`, `packages/api-client`, `packages/auth`, `packages/ui`.
- [ ] Register six SPA app registrations (two per environment) with redirect URIs under the Front Door host and localhost for dev.
- [ ] Set Assignment Required on `pipeline-web-admin` and assign `PIPELINE-Admins` only.
- [ ] Define Front Door routes and origin groups for the two Static Web Apps and the API.
- [ ] Correct TDD 4.3 and the Entra guide section 2 wording on Conditional Access.
