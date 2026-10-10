# Security assessment

Independent review of authentication, authorization, isolation, input handling, secrets, and
dependency posture, verified against `architecture/SECURITY.md`, TO_BE §6.1, and the TDD. Tested live
against the running stack with real RS256 tokens from the local issuer. Azure-only controls (Entra
managed-identity DB auth, WAF, Private Link, Conditional Access, Defender upload scanning) are noted
as not verifiable locally.

## Posture summary

The identity and isolation boundary is strong and was exercised adversarially with no critical or high
break. The security findings are one configuration-hardening gap (A1), a forensic-integrity gap (A5),
and defense-in-depth / hygiene items. The most severe audit finding overall, B-01, is a
concurrency-control bypass with a security dimension (it also writes non-removable duplicate rows into
the immutable audit ledger) and is covered in the technical findings and risk register.

## Verified controls (attempted bypass, held)

| Control | Test | Result |
|---|---|---|
| Token required | 33 operations probed with no token | all 401 |
| Signature / algorithm | `alg:none`; HS256 signed with the RSA public key | all 401; `algorithms` pinned to RS256 |
| Claim validation | wrong aud / iss / azp / tid; expired; app-only (no scp) | all 401 |
| Role gating | no-role user on all 33 routes | all 403 |
| Tenant isolation | coordinator A reads/writes coordinator B's site | 404 (no object-existence leak); cross-write rowcount 0 |
| RLS fail-closed | app login, no session context, 7 protected tables | 0 rows |
| Ledger immutability | UPDATE/DELETE on `auditoria`, `sitio_estatus_historial`; ALTER the security policy; touch `alembic_version` | all denied at the DB (Msg 37359 / 229 / permission) |
| Idempotency scope | coordinator B replays A's Idempotency-Key | not honoured across users |
| Error hygiene | dozens of malformed inputs | 422/404, no 500, no SQL or exception text echoed to the client |
| Log redaction | PII keys (nombre, telefono, correo, token, authorization) | redacted before output |

## Vulnerabilities and gaps

### A1 — Production guard does not validate the JWKS URL (Medium)
- Attack scenario: a production deployment is configured with the correct Entra issuer string but a
  JWKS endpoint the attacker controls (misconfiguration or tampering). The start-up guard accepts it;
  the API then fetches signing keys from the attacker and would trust tokens the attacker signs.
- Why not High: a wrong JWKS fails closed — every legitimate token 401s immediately, so the condition
  is loud — and the attacker additionally needs a reachable malicious JWKS host.
- Mitigation status: **fixed and verified** (test `test_production_guard_refuses_foreign_jwks_url`). `_production_guard` now requires `auth_jwks_url` to be the Entra keys host.

### A5 — Client-controlled headers written into the immutable audit ledger (Low)
- Attack scenario: any authenticated coordinator sends `X-Forwarded-For` and `X-Correlation-Id` of
  their choosing; those exact values are stored in the append-only `auditoria` ledger, permanently
  poisoning the forensic trail that SECURITY.md relies on for incident response.
- No identity impact: the actor oid is taken from the token, not from a header.
- Mitigation status: open. Generate the correlation id server-side (log any client value separately)
  and trust `X-Forwarded-For` only from configured proxy ranges. Fix with D-12
  (`--forwarded-allow-ips "*"`), which is the transport-level half of the same issue.

### A2 — Unknown role string reaches the DB session context (Low, latent)
- Mechanism: `validate_token` does not require a known role; `primary_role` returns the first role
  verbatim for any unrecognised role, and that string becomes `SESSION_CONTEXT('rol')`, which RLS
  honours for `Admin`/`Sistema`. A single un-gated route plus a forged `roles:["Sistema"]` token would
  bypass RLS entirely.
- Why Low: every one of the 33 routes is role-gated today, and `Sistema` is a server-side DB role, not
  an Entra appRole, so no issued token can carry it. This is defense-in-depth against a future
  un-gated route.
- Mitigation status: open. `primary_role` → `"Ninguno"` for unknown roles; optionally reject tokens
  with no known role at validation.

### Isolation architecture note (not a finding)
RLS predicates cover the seven tables that carry `coordinador_oid`. The admin-only tables
(`auditoria`, `coordinador_equivalencia`, `carga_*`) have no RLS and rely solely on
`require_role(Admin)` — a single enforced layer, which is why A2 matters as defense-in-depth. TO_BE §5
also claims a database trigger enforces the denormalised `coordinador_oid` on child tables; no such
trigger exists (B-07), so that layer is code-only.

### Info-level hygiene (A3/A4/A6)
No Front-Door-id header check at the API (origin restriction is network-only, and SECURITY.md labels
the header check a recommendation); the dev IdP compose port is not bound to loopback, so `/token` is
LAN-reachable in local development; `/readyz` returns exception class names unauthenticated.

## Secrets and dependencies

- No secrets committed: `gitleaks` over the history found none; `.env*` is git-ignored (with the
  D-01 side effect that `.env.example` itself is untracked); only the two dev `.env.development`
  files and the public well-known Azurite dev key are present, both clearly dev-only.
- `pnpm audit` (high) and `pip-audit` on the locked dependencies both report no known vulnerabilities.
- GitHub Actions are pinned to floating tags rather than commit SHAs (D-09) — a supply-chain exposure
  in workflows that hold `id-token: write` and push images.

## Not verifiable locally
Entra managed-identity database authentication, Front Door WAF behaviour, Private Link, Conditional
Access, Defender for Storage upload scanning, and Key Vault reference resolution are written and at
most statically validated; none was exercised because no Azure subscription exists.
