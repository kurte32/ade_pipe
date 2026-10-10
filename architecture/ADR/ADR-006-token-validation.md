# ADR-006: Token validation, client restrictions, and role assignment

**Status:** Proposed  **Date:** 2026-10-10  **Deciders:** Subdirección de IA, Identidad, Seguridad

## Context and problem statement

The Entra guide (Part C) validates signature, issuer (v1 and v2), audience, expiry, and the presence of an app role. It derives the coordinador identity from `oid`. For production the validation must be tightened, the admin web must be restricted to administrators at sign-in, roles must be assigned sustainably, and the backend needs a way to resolve a coordinador's email to an `oid` for the equivalence table (TDD RF-09, 8.3), which no document designs.

## Requirements and constraints

- Fact (TDD 5.1): single tenant, corporate accounts only, app roles `Coordinador` and `Admin` assigned to groups, PKCE, short-lived tokens, MFA by Conditional Access.
- Fact (TDD 5.2 layer 1): the coordinador identifier comes only from the token claim `oid`.
- Fact (Entra guide A4, A9): roles defined on `pipeline-api`, assigned to groups `PIPELINE-Coordinadores` and `PIPELINE-Admins`; group-to-role assignment may require an Entra ID P1 licence (guide's caveat, verify with Identidad).
- Fact (Entra guide A5): the API manifest should request v2 access tokens.
- Fact (TDD 8.3): a `USUARIO` whose equivalence does not resolve to an Entra account is a load error.
- Fact (verified in Learn): Conditional Access targets the resource application; group targeting differentiates administrators.
- Assumption: no application permissions are defined on `pipeline-api`, but validation must not rely on that staying true.

## Options considered

### Option A: Strict validation (v2 issuer only, `aud`, `tid`, `exp`, `scp` contains `access_as_user`, `azp` in SPA allowlist, role required), Assignment Required on API and admin SPA, group-based roles, Graph `User.ReadBasic.All` for oid resolution

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Cost | None (P1 licence if not already present, verify) |
| Security | Rejects app-only tokens, tokens from other clients, other tenants, v1 tokens |
| Reliability | JWKS cached with refresh on unknown `kid` |
| Team familiarity | High (PyJWT as in the guide) |

Pros: defence in depth with a few lines; admin web unreachable to coordinadores; oid resolution automated.
Cons: `azp` allowlist must be updated when a registration is added; depends on P1 for group assignment.

### Option B: Guide as written (v1 and v2 issuers, roles only)

| Dimension | Assessment |
|---|---|
| Complexity | Lowest |
| Cost | None |
| Security | Accepts any client in the tenant that can obtain a token for the API; would accept app-only tokens with roles |
| Reliability | Same |
| Team familiarity | High |

Pros: already drafted and locally tested.
Cons: insufficient for production.

### Option C: Delegate validation to a gateway (API Management with `validate-jwt`)

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Cost | Adds a service |
| Security | Equivalent |
| Reliability | One more hop |
| Team familiarity | Medium |

Pros: policy-driven.
Cons: API Management was rejected in TO_BE section 8; the API must still read claims for RLS, so validation in the API is unavoidable.

## Decision and rationale

Option A. Validation stays in the API because the same claims drive `SESSION_CONTEXT`. The additional checks cost little and close real gaps: v1 tokens, tokens minted for other clients, and any future app-only tokens. Assignment Required on `pipeline-web-admin` ensures a coordinador never reaches the admin web, independent of role checks. Email to `oid` resolution happens through Graph when an administrator saves an equivalence, and is revalidated at every carga.

## Advantages and disadvantages

Advantages: small, testable `identity` module; one allowlist in configuration per environment; equivalences cannot reference non-existent accounts.
Disadvantages: six SPA client ids across environments to maintain in the allowlist; group-based assignment depends on licensing; `User.ReadBasic.All` is an application permission that Identidad must consent to.

## Security, reliability, and cost implications

Security: the API never accepts a coordinador id from a parameter; `oid` is stable where UPN can change, so equivalences store `oid` and use email only for lookup; `roles` is required to contain exactly one of the two values; a token with both roles is accepted as Admin and logged. Tokens are never logged.
Reliability: `PyJWKClient` with caching and a retry on unknown `kid` for key rollover; Entra outage does not affect already-issued tokens until expiry.
Cost: possible P1 licence; otherwise none.

## Consequences and risks

- The identity request message (guide section 8) gains: `requestedAccessTokenVersion = 2`, Assignment Required on `pipeline-web-admin`, application permission `User.ReadBasic.All` (and later `TeamsActivity.Send`, ADR-007) for the backend managed identity, group-targeted Conditional Access policies.
- If P1 is unavailable, users are assigned to roles directly; at ten users this is manageable and must be documented as an operational procedure.
- Risk: a misconfigured `azp` allowlist locks everyone out; the allowlist is validated at startup and covered by integration tests per environment.

## Conditions that would justify revisiting

- Application permissions are added to `pipeline-api` for the AI agent or another service; then the API needs an explicit app-only path with its own authorization.
- A third client is introduced.
- The organization adopts a central gateway that performs JWT validation for all APIs.

## Action items

- [ ] Update `auth.py` from the guide: single v2 issuer, `tid`, `scp`, `azp` allowlist, role presence, startup validation of configuration.
- [ ] Add integration tests for each rejection path, including app-only token shape and wrong `azp`.
- [ ] Request Assignment Required on `pipeline-web-admin` and `User.ReadBasic.All` for the managed identity.
- [ ] Confirm P1 availability for group-to-role assignment; document the direct-assignment fallback.
- [ ] Implement equivalence save with Graph lookup and revalidation during carga.
